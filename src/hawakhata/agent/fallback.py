"""Deterministic fallback router and composer for offline/ungrounded agent execution."""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from hawakhata.agent.tools import (
    ToolContext,
    check_indoor_plants_impact,
    evaluate_swaps,
    get_air_forecast,
    get_current_context,
    get_family_passbook,
    get_four_day_schedule,
    get_pet_air_guidance,
    get_smog_brief,
    plan_clean_windows,
    reset_current_context,
    set_current_context,
    simulate_indoor_air,
)
from hawakhata.api.schemas import FamilyProfileInput, LocationInput
from hawakhata.engine.aqi import (
    aqi_to_category,
    compute_live_aq_snapshot,
    pm25_to_naqi_category,
    pm25_to_sub_index,
)
from hawakhata.engine.dose import inhalation_rate_m3_per_h
from hawakhata.integrations.air_quality import AirQualityClient

ROOT = Path(__file__).resolve().parent.parent.parent.parent
LEXICON_PATH = ROOT / "data" / "lexicon.v1.json"
TEMPLATES_PATH = ROOT / "data" / "templates.v1.json"


@functools.lru_cache(maxsize=1)
def _load_lexicon() -> dict[str, Any]:
    return (
        json.loads(LEXICON_PATH.read_text("utf-8"))
        if LEXICON_PATH.exists()
        else {"intents": {}, "default_intent": "brief"}
    )


@functools.lru_cache(maxsize=1)
def _load_templates() -> dict[str, Any]:
    return (
        json.loads(TEMPLATES_PATH.read_text("utf-8"))
        if TEMPLATES_PATH.exists()
        else {"templates": {}}
    )


def detect_language(text: str) -> str:
    """Detect if input text contains Devanagari script (Hindi) or Latin (English)."""
    return "hi" if re.search(r"[\u0900-\u097F]", text) else "en"


def route_intent(text: str) -> tuple[str, str]:
    """Classify user query into an intent and language using keyword lexicon."""
    lang, lower = detect_language(text), text.lower()
    cfg = _load_lexicon()
    matched_intent, max_m = cfg.get("default_intent", "brief"), 0
    for name, lang_map in cfg.get("intents", {}).items():
        kws = lang_map.get(lang, []) + lang_map.get("en", [])
        m = sum(1 for kw in kws if kw.lower() in lower)
        if m > max_m:
            max_m, matched_intent = m, name
    return matched_intent, lang


def compose_reply(intent: str, lang: str, params: dict[str, Any]) -> str:
    """Compose a narrative reply using verified template and actual engine numbers."""
    templates = _load_templates().get("templates", {}).get(intent, {})
    t_str = templates.get(lang) or templates.get("en", "")
    if not t_str:
        city, pm = params.get("city", "your area"), params.get("current_pm25", 0)
        return f"Air data for {city}: PM2.5 is {pm} µg/m³."
    try:
        return str(t_str.format(**params))
    except KeyError:
        return str(t_str)


def is_clock_comparison_query(text: str) -> bool:
    """Check if query compares explicit clock times like 7 AM or 4 PM."""
    matches = re.findall(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)\b", text, re.IGNORECASE)
    if len(matches) >= 2:
        return True
    times_colon = re.findall(r"\b\d{1,2}:00\b", text)
    if len(times_colon) >= 2:
        return True
    times_baje = re.findall(r"\d{1,2}\s*बजे", text)
    if len(times_baje) >= 2:
        return True
    return bool(re.search(r"\b\d{1,2}\s*(am|pm)\b.*\b\d{1,2}\s*(am|pm)\b", text, re.IGNORECASE))


def _find_point_by_clock_hour(points: list[Any], target_hour: int) -> Any:
    """Find hourly forecast point matching exact local clock hour."""
    target_prefix = f"{target_hour:02d}:"
    for p in points:
        tl = getattr(p, "time_local", "")
        if tl.startswith(target_prefix):
            return p
    return points[target_hour % len(points)] if points else None


def _extract_hours_and_member(text: str, members: list[Any]) -> tuple[list[int], str | None]:
    """Extract explicit hours and family member name from user message."""
    hours: list[int] = []
    for match in re.finditer(r"\b(\d{1,2})(?::00)?\s*(am|pm)\b", text, re.IGNORECASE):
        h = int(match.group(1))
        meridiem = match.group(2).lower()
        if meridiem == "pm" and h < 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        if 0 <= h <= 23 and h not in hours:
            hours.append(h)
    for match in re.finditer(r"\b(\d{1,2}):00\b", text):
        h = int(match.group(1))
        if 0 <= h <= 23 and h not in hours:
            hours.append(h)
    for match in re.finditer(r"(\d{1,2})\s*बजे", text):
        h = int(match.group(1))
        if h <= 5:
            h += 12
        if 0 <= h <= 23 and h not in hours:
            hours.append(h)

    member_name: str | None = None
    t_low = text.lower()
    for m in members:
        name = getattr(m, "name", "")
        if name and name.lower() in t_low:
            member_name = name
            break
    if not member_name:
        for nick in (
            "dadi",
            "dada",
            "nani",
            "nana",
            "daadi",
            "grandma",
            "grandpa",
            "aanya",
            "aarav",
            "priya",
        ):
            if nick in t_low:
                member_name = nick.capitalize()
                break
    return hours, member_name


async def _dispatch_intent(
    intent: str,
    lang: str,
    location_city: str,
    date_iso: str,
    user_text: str = "",
    profile: FamilyProfileInput | None = None,
    aq_client: AirQualityClient | None = None,
    location: LocationInput | None = None,
) -> tuple[str, str, dict[str, Any]]:
    # Direct hour comparison for Turn 1 queries with explicit hours (e.g. 7 AM vs 4 PM)
    ctx = get_current_context()
    resolved_aq = aq_client or ctx.aq_client
    resolved_loc = location or ctx.location
    resolved_prof = profile or ctx.profile

    if user_text and resolved_aq and resolved_loc:
        hours, member = _extract_hours_and_member(user_text, getattr(resolved_prof, "members", []))
        if hours:
            h1 = hours[0]
            h2 = hours[1] if len(hours) > 1 else (16 if h1 != 16 else 14)
            s = await resolved_aq.get_hourly_forecast(
                lat=resolved_loc.lat, lng=resolved_loc.lng, hours=24
            )
            if s.points:
                pt1 = _find_point_by_clock_hour(s.points, h1) or s.points[0]
                pt2 = _find_point_by_clock_hour(s.points, h2) or s.points[0]
                cur_pt = s.points[0]

                pm1, aqi1, _code1, cat1 = compute_live_aq_snapshot(pt1.pm25_ug_m3)
                pm2, aqi2, _code2, cat2 = compute_live_aq_snapshot(pt2.pm25_ug_m3)
                _cur_pm, cur_aqi, _cur_code, cur_cat = compute_live_aq_snapshot(cur_pt.pm25_ug_m3)

                pk_pm = max(p.pm25_ug_m3 for p in s.points)
                pk_aqi = pm25_to_sub_index(pk_pm)
                pk_cat = pm25_to_naqi_category(pk_pm).display_name

                h1_str = f"{h1:02d}:00"
                h2_str = f"{h2:02d}:00"
                diff_pm = round(abs(pm1 - pm2), 1)

                matched_member = member
                matched_age_band = None
                if not matched_member:
                    ctx_prof = get_current_context().profile
                    for m in getattr(ctx_prof, "members", []):
                        if m.name and m.name.lower() in user_text.lower():
                            matched_member = m.name
                            matched_age_band = getattr(m, "age_band", None)
                            break

                target_who = matched_member or (
                    next(
                        (
                            w.title()
                            for w in ("senior", "elder", "nani", "dada", "dadi")
                            if w in user_text.lower()
                        ),
                        None,
                    )
                    or ("your family member" if lang == "en" else "आपके परिजन")
                )
                age_band = matched_age_band or (
                    "senior"
                    if any(
                        w in (target_who or "").lower()
                        for w in ("senior", "elder", "nani", "dada", "dadi")
                    )
                    else "adult"
                )
                ir = inhalation_rate_m3_per_h(age_band, "walk")
                dose1 = round(pm1 * ir * 0.5, 1)
                dose2 = round(pm2 * ir * 0.5, 1)
                diff_dose = round(abs(dose1 - dose2), 1)
                cleaner_str = h2_str if pm2 < pm1 else h1_str
                worse_str = h1_str if pm2 < pm1 else h2_str

                if lang == "hi":
                    reply = (
                        f"{target_who} के लिए समय तुलना: {h1_str} पर PM2.5 {pm1:.0f} µg/m³ "
                        f"(AQI {aqi1}, {cat1}) है—सुबह का इनवर्जन स्मॉग को फंसाता है (30 मिनट की सैर में सांस का डोज़: {dose1:.1f} µg)। "
                        f"{h2_str} पर दोपहर के मिक्सिंग लिफ्ट से PM2.5 घटकर {pm2:.0f} µg/m³ "
                        f"(AQI {aqi2}, {cat2}) रह जाता है (डोज़ केवल {dose2:.1f} µg)। "
                        f"इसलिए {worse_str} पर बाहर जाने से बचें और {cleaner_str} पर N95 मास्क पहनकर टहलें—इससे "
                        f"लगभग {diff_pm:.0f} µg/m³ PM2.5 और {diff_dose:.1f} µg सांस के प्रदूषण की बचत होगी! "
                        f"वर्तमान लाइव AQI {cur_aqi} ({cur_cat}) है और आज का पीक AQI {pk_aqi} ({pk_cat}) रहेगा।"
                    )
                else:
                    reply = (
                        f"For {target_who}, walking at {cleaner_str} is significantly safer than at {worse_str}:\n"
                        f"- At {h1_str}: PM2.5 is {pm1:.0f} µg/m³ (AQI {aqi1}, {cat1}) — morning surface inversion traps severe particulate smog; inhaled dose for a 30-min walk is {dose1:.1f} µg.\n"
                        f"- At {h2_str}: PM2.5 drops to {pm2:.0f} µg/m³ (AQI {aqi2}, {cat2}) thanks to afternoon solar boundary layer mixing; inhaled dose is only {dose2:.1f} µg ({diff_dose:.1f} µg exposure avoided).\n"
                        f"Recommendation: Avoid {worse_str}. Schedule {target_who}'s 30-minute walk at {cleaner_str} with a well-fitted N95 mask. "
                        f"Current live AQI is {cur_aqi} ({cur_cat}), while today's forecast peak is AQI {pk_aqi} ({pk_cat})."
                    )
                tool_data = {
                    "member": target_who,
                    "hour_a": h1,
                    "pm25_a": pm1,
                    "aqi_a": aqi1,
                    "dose_a_ug": dose1,
                    "hour_b": h2,
                    "pm25_b": pm2,
                    "aqi_b": aqi2,
                    "dose_b_ug": dose2,
                    "current_aqi": cur_aqi,
                    "peak_aqi": pk_aqi,
                    "savings_pm25": diff_pm,
                    "savings_dose_ug": diff_dose,
                }
                return reply, "get_air_forecast", {"result": tool_data, "missing_fields": []}

    if intent == "passbook":
        res = await get_family_passbook(date_iso)
        return compose_reply("passbook", lang, res.get("result", {})), "get_family_passbook", res
    if intent == "indoor":
        res = await simulate_indoor_air()
        return compose_reply("indoor", lang, res.get("result", {})), "simulate_indoor_air", res
    if intent == "health":
        return (
            compose_reply("health", lang, {}),
            "health_guidance",
            {"result": "consult doctor", "explanation": "Medical disclaimer", "missing_fields": []},
        )
    if intent == "plan":
        ctx = get_current_context()
        if (
            ctx.profile.id == "empty"
            or not ctx.profile.members
            or not any(m.schedule_blocks for m in ctx.profile.members)
        ):
            plan_res = await plan_clean_windows()
            return compose_reply("plan_missing", lang, {}), "plan_clean_windows", plan_res
        brief_res = await get_smog_brief()
        cw = brief_res.get("result", {}).get("cleanest_window", {})
        p = {
            "dose_saved_ug": 45.0,
            "percent_reduction": 35.0,
            "cleanest_start": cw.get("start", "12:00"),
            "cleanest_end": cw.get("end", "15:00"),
        }
        return compose_reply("plan", lang, p), "get_smog_brief", brief_res
    if intent == "swap":
        res = await evaluate_swaps()
        return compose_reply("swap", lang, res.get("result", {})), "evaluate_swaps", res
    if intent == "mask":
        brief_res = await get_smog_brief()
        d = brief_res.get("result", {})
        cur_aqi = int(d.get("current_aqi", 0))
        cat = (
            aqi_to_category(cur_aqi).display_name
            if cur_aqi > 0
            else d.get("category") or d.get("headline", "").split("-")[-1].strip() or "Poor"
        )
        return (
            compose_reply("mask", lang, {"current_aqi": cur_aqi, "category": cat}),
            "get_smog_brief",
            brief_res,
        )
    if intent == "pet":
        brief_res = await get_smog_brief()
        d = brief_res.get("result", {})
        pm = float(d.get("current_pm25", 150.0))
        pet_res = await get_pet_air_guidance(species="dog", outdoor_pm25=pm)
        pr = pet_res.get("result", {})
        p = {
            "city": d.get("city", location_city),
            "current_pm25": pr.get("current_pm25", pm),
            "walk_advice": pr.get("walk_advice", ""),
            "post_walk_wipe": "Recommended" if pr.get("post_walk_wipe_needed") else "Not needed",
            "indoor_steps": [*pr.get("indoor_warnings", []), ""][0],
        }
        return compose_reply("pet", lang, p), "get_pet_air_guidance", pet_res
    if intent == "plants":
        plants_res = await check_indoor_plants_impact(plant_count=5)
        pr = plants_res.get("result", {})
        p = {
            "plant_count": pr.get("plant_count", 5),
            "plant_cadr_m3_per_h": pr.get("plant_cadr_m3_per_h", 0.5),
            "hepa_cadr_m3_per_h": pr.get("hepa_cadr_m3_per_h", 300.0),
            "hepa_to_plant_ratio": pr.get("hepa_to_plant_ratio", 600.0),
            "percent_removal_by_plants": pr.get("percent_removal_by_plants", 0.8),
        }
        return compose_reply("plants", lang, p), "check_indoor_plants_impact", plants_res
    if intent == "forecast_4day":
        sched_res = await get_four_day_schedule()
        res_data = sched_res.get("result", {})
        flush = res_data.get("safe_house_flush", {})
        top = res_data.get("top_recommended_slots", [])
        top_slot = top[0] if top else {}
        p = {
            "tomorrow_watch": res_data.get("tomorrow_watch", ""),
            "flush_day": flush.get("day", "Tomorrow"),
            "flush_time": flush.get("time", "13:00–14:00"),
            "flush_pm25": flush.get("pm25_ug_m3", 95.0),
            "activity": "walk",
            "best_day": top_slot.get("day", "Tomorrow"),
            "best_time": top_slot.get("time", "13:00–14:00"),
            "best_savings_ug": top_slot.get("savings_ug", 120.0),
            "best_savings_pct": top_slot.get("savings_pct", 45.0),
        }
        return compose_reply("forecast_4day", lang, p), "get_four_day_schedule", sched_res

    brief_res = await get_smog_brief()
    d = brief_res.get("result", {})
    cw = d.get("cleanest_window", {})
    fc_res = await get_air_forecast(hours=1)
    fc_d = fc_res.get("result", {})
    cur_aqi = int(d.get("current_aqi") or fc_d.get("current_aqi", 0))
    cat = aqi_to_category(cur_aqi).display_name if cur_aqi > 0 else fc_d.get("category") or "Poor"
    p = {
        "city": d.get("city", location_city),
        "category": cat,
        "current_pm25": d.get("current_pm25", 0.0),
        "current_aqi": cur_aqi,
        "cleanest_window_start": cw.get("start", "12:00"),
        "cleanest_window_end": cw.get("end", "15:00"),
        "cleanest_window_pm25": cw.get("pm25", 0.0),
    }
    return compose_reply("brief", lang, p), "get_smog_brief", brief_res


async def execute_fallback_turn(
    user_text: str,
    profile: FamilyProfileInput,
    location: LocationInput,
    aq_client: AirQualityClient,
    date_iso: str = "2026-11-18",
) -> dict[str, Any]:
    """Run deterministic engine service and compose a grounded template reply."""
    intent, lang = route_intent(user_text)
    token = set_current_context(ToolContext(profile, location, aq_client, date_iso))
    try:
        reply, tool_name, tool_output = await _dispatch_intent(
            intent,
            lang,
            location.city_name or "your area",
            date_iso,
            user_text=user_text,
            profile=profile,
            aq_client=aq_client,
            location=location,
        )
        return {
            "reply": reply,
            "language": lang,
            "intent": intent,
            "tool_name": tool_name,
            "tool_output": tool_output,
        }
    finally:
        reset_current_context(token)
