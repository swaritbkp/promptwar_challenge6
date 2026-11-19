"""Passbook service orchestrating personal and family air accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hawakhata.api.schemas import FamilyProfileInput
from hawakhata.engine.aqi import pm25_to_naqi_category, pm25_to_sub_index
from hawakhata.engine.budget import PassbookEntry, build_passbook_entry
from hawakhata.engine.dose import ScheduleBlock, build_member_timeline, compute_member_dose
from hawakhata.engine.indoor_model import IndoorSourceEvent, simulate_indoor_pm25


@dataclass(frozen=True, slots=True)
class FamilyPassbookResult:
    """Consolidated family air passbook summary across all household members."""

    family_id: str
    family_name: str
    entries: list[dict[str, Any]]
    total_budget_ug: float
    total_debit_ug: float
    net_balance_ug: float
    highest_debit_member: str
    cigarette_equivalent: float
    current_aqi: int = 317
    current_category: str = "very_poor"
    current_category_label: str = "Very Poor"
    peak_pm25: float = 380.0
    cleanest_window: str = "12:00 – 15:00"


def compute_family_passbook(
    profile: FamilyProfileInput,
    outdoor_pm25_series: list[float],
) -> FamilyPassbookResult:
    """Compute 24-hour air passbook entries for all family members."""
    indoor_home_series: list[float] | None = None
    if profile.rooms:
        r = profile.rooms[0]
        events = [
            IndoorSourceEvent(s.kind, s.start_hour, s.minutes, s.count) for s in profile.sources
        ]
        sim = simulate_indoor_pm25(
            room_volume_m3=r.volume_m3,
            outdoor_pm25_series=outdoor_pm25_series,
            windows_open_hours=set(r.windows_open_hours),
            purifier_cadr_m3_per_h=r.purifier_cadr_m3_per_h,
            purifier_on_hours=set(r.purifier_on_hours),
            source_events=events,
        )
        indoor_home_series = sim.hourly_pm25_ug_m3

    entries: list[dict[str, Any]] = []
    tot_budget, tot_debit, max_debit, max_mbr = 0.0, 0.0, -1.0, ""
    tot_cigs = 0.0

    for m in profile.members:
        blocks = [
            ScheduleBlock(b.start_hour, b.end_hour, b.micro_env, b.activity, b.label or b.activity)
            for b in m.schedule_blocks
        ]
        tl = build_member_timeline(blocks)
        dose = compute_member_dose(m.age_band, tl, outdoor_pm25_series, indoor_home_series)
        entry: PassbookEntry = build_passbook_entry(
            m.id,
            m.name,
            m.age_band,
            dose.total_dose_ug,
            dose.hourly_doses_ug,
            dose.top_contributors,
        )
        entries.append(asdict(entry))
        tot_budget += entry.budget_ug
        tot_debit += entry.debit_ug
        tot_cigs += entry.cigarette_equivalent
        if entry.debit_ug > max_debit:
            max_debit, max_mbr = entry.debit_ug, m.name

    cur_pm = outdoor_pm25_series[0] if outdoor_pm25_series else 150.0
    cur_aqi = pm25_to_sub_index(cur_pm)
    cat = pm25_to_naqi_category(cur_pm)
    pk_pm = max(outdoor_pm25_series) if outdoor_pm25_series else 150.0

    best_start, best_avg = 12, float("inf")
    if len(outdoor_pm25_series) >= 3:
        for i in range(len(outdoor_pm25_series) - 2):
            win_avg = sum(outdoor_pm25_series[i : i + 3]) / 3.0
            if win_avg < best_avg:
                best_avg, best_start = win_avg, i
        clean_win = f"{best_start:02d}:00 – {best_start + 3:02d}:00"
    else:
        clean_win = "12:00 – 15:00"

    return FamilyPassbookResult(
        family_id=profile.id,
        family_name=profile.name,
        entries=entries,
        total_budget_ug=round(tot_budget, 2),
        total_debit_ug=round(tot_debit, 2),
        net_balance_ug=round(tot_budget - tot_debit, 2),
        highest_debit_member=max_mbr,
        cigarette_equivalent=round(tot_cigs, 1),
        current_aqi=cur_aqi,
        current_category=cat.code,
        current_category_label=cat.display_name,
        peak_pm25=round(pk_pm, 1),
        cleanest_window=clean_win,
    )


@dataclass(frozen=True, slots=True)
class HouseholdTriageItem:
    """Prioritized protection recommendation for a vulnerable household member."""

    member_id: str
    name: str
    priority_rank: int
    vulnerability_score: float
    debit_to_budget_ratio: float
    sensitivities: list[str]
    primary_action: str


def rank_household_triage(
    profile: FamilyProfileInput, passbook: FamilyPassbookResult
) -> list[HouseholdTriageItem]:
    """Rank household members by dose burden and clinical sensitivity multipliers."""
    sens_mult = {
        "asthma": 2.0,
        "cardiovascular": 1.9,
        "copd": 2.2,
        "pregnancy": 2.0,
        "infant": 2.0,
        "senior": 1.7,
        "child": 1.5,
    }
    candidates = []
    for m in profile.members:
        entry = next((e for e in passbook.entries if e.get("member_label") == m.name), None)
        debit = float(entry.get("debit_ug", 0.0)) if entry else 0.0
        budget = float(entry.get("budget_ug", 1.0)) if entry else 1.0
        ratio = round(debit / max(1.0, budget), 2)
        mult = 1.0
        if m.age_band in ("0_1", "1_2", "2_3", "3_6", "6_11", "child"):
            mult *= 1.5
        elif m.age_band in ("61_71", "71_81", "81_plus", "senior"):
            mult *= 1.7
        for s in m.sensitivities:
            mult *= sens_mult.get(s.lower(), 1.3)
        score = round(ratio * mult, 2)
        action = (
            "Priority 1: Dedicate HEPA purifier bedroom; N95 respirator outdoors."
            if score >= 3.0
            else (
                "Priority 2: Shift routine to 12:00-15:00 clean window; seal room cracks."
                if score >= 1.8
                else "Priority 3: General routine air protection."
            )
        )
        candidates.append((score, m.id, m.name, ratio, list(m.sensitivities), action))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [
        HouseholdTriageItem(
            member_id=cid,
            name=cname,
            priority_rank=idx + 1,
            vulnerability_score=cscore,
            debit_to_budget_ratio=cratio,
            sensitivities=csens,
            primary_action=cact,
        )
        for idx, (cscore, cid, cname, cratio, csens, cact) in enumerate(candidates)
    ]


def generate_shareable_digest(
    profile: FamilyProfileInput,
    passbook: FamilyPassbookResult,
    city_name: str = "Delhi NCR",
    date_str: str = "Today",
) -> str:
    """Generate a clean, copy/print-friendly daily passbook summary."""
    triage = rank_household_triage(profile, passbook)
    top = triage[0] if triage else None
    cigs = round(passbook.total_debit_ug / 22.0, 1)
    status_icon = "⚠️" if passbook.net_balance_ug < 0 else "✅"
    lines = [
        f"📋 HawaKhata Passbook Digest — {city_name} ({date_str})",
        "━" * 38,
        f"• Family Air Debit: {passbook.total_debit_ug:.0f} µg ({cigs} cigs equiv)",
        f"• WHO Air Budget: {passbook.total_budget_ug:.0f} µg | Balance: {passbook.net_balance_ug:+.0f} µg {status_icon}",
    ]
    if top:
        sens = f" ({', '.join(top.sensitivities)})" if top.sensitivities else ""
        lines.append(
            f"• Highest Priority: {top.name}{sens} — {top.debit_to_budget_ratio:.1f}× WHO budget"
        )
        lines.append(f"• Key Action: {top.primary_action}")
    lines.extend(["━" * 38, "Deterministic science by HawaKhata (हवा खाता)"])
    return "\n".join(lines)
