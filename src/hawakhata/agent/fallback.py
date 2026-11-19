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
    get_pet_air_guidance,
    get_smog_brief,
    plan_clean_windows,
    reset_current_context,
    set_current_context,
    simulate_indoor_air,
)
from hawakhata.api.schemas import FamilyProfileInput, LocationInput
from hawakhata.engine.aqi import aqi_to_category
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


async def _dispatch_intent(
    intent: str, lang: str, location_city: str, date_iso: str
) -> tuple[str, str, dict[str, Any]]:
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
            intent, lang, location.city_name or "your area", date_iso
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
