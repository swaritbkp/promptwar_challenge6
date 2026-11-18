"""Passbook service orchestrating personal and family air accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hawakhata.api.schemas import FamilyProfileInput
from hawakhata.engine.budget import PassbookEntry, build_passbook_entry
from hawakhata.engine.dose import ScheduleBlock, build_member_timeline, compute_member_dose
from hawakhata.engine.indoor_model import IndoorSourceEvent, simulate_indoor_pm25


@dataclass(frozen=True, slots=True)
class FamilyPassbookResult:
    """Consolidated family air passbook summary across all household members.

    Attributes:
        family_id: Unique household identifier.
        family_name: Display name for the household.
        entries: Detailed passbook entries for each individual member.
        total_budget_ug: Aggregate allowable daily PM2.5 inhalation budget for the family.
        total_debit_ug: Aggregate inhaled PM2.5 across all members.
        net_balance_ug: Remaining budget (positive) or total excess overage (negative).
        highest_debit_member: Label of the member who inhaled the highest particulate mass.
    """

    family_id: str
    family_name: str
    entries: list[dict[str, Any]]
    total_budget_ug: float
    total_debit_ug: float
    net_balance_ug: float
    highest_debit_member: str


def compute_family_passbook(
    profile: FamilyProfileInput,
    outdoor_pm25_series: list[float],
) -> FamilyPassbookResult:
    """Compute 24-hour air passbook entries for all family members.

    Args:
        profile: Validated household profile with members, schedule blocks, and rooms.
        outdoor_pm25_series: 24-hour sequence of outdoor ambient PM2.5 in ug/m3.

    Returns:
        FamilyPassbookResult detailing individual entries and aggregate metrics.
    """
    # 1. Simulate indoor home PM2.5 if room specifications exist
    indoor_home_series: list[float] | None = None
    if profile.rooms:
        primary_room = profile.rooms[0]
        events = [
            IndoorSourceEvent(
                kind=s.kind,
                start_hour=s.start_hour,
                minutes=s.minutes,
                count=s.count,
            )
            for s in profile.sources
        ]
        indoor_sim = simulate_indoor_pm25(
            room_volume_m3=primary_room.volume_m3,
            outdoor_pm25_series=outdoor_pm25_series,
            windows_open_hours=set(primary_room.windows_open_hours),
            purifier_cadr_m3_per_h=primary_room.purifier_cadr_m3_per_h,
            purifier_on_hours=set(primary_room.purifier_on_hours),
            source_events=events,
        )
        indoor_home_series = indoor_sim.hourly_pm25_ug_m3

    entries: list[dict[str, Any]] = []
    total_budget = 0.0
    total_debit = 0.0
    highest_debit = -1.0
    highest_member = ""

    for member in profile.members:
        blocks = [
            ScheduleBlock(
                start_hour=b.start_hour,
                end_hour=b.end_hour,
                micro_env=b.micro_env,
                activity=b.activity,
                label=b.label or b.activity,
            )
            for b in member.schedule_blocks
        ]
        timeline = build_member_timeline(blocks)
        dose_res = compute_member_dose(
            age_band=member.age_band,
            timeline=timeline,
            outdoor_pm25_series=outdoor_pm25_series,
            indoor_home_series=indoor_home_series,
        )
        passbook_entry: PassbookEntry = build_passbook_entry(
            member_label=member.name,
            age_band=member.age_band,
            debit_ug=dose_res.total_dose_ug,
            hourly_doses_ug=dose_res.hourly_doses_ug,
            top_contributors=dose_res.top_contributors,
        )

        entry_dict = asdict(passbook_entry)
        entries.append(entry_dict)

        total_budget += passbook_entry.budget_ug
        total_debit += passbook_entry.debit_ug

        if passbook_entry.debit_ug > highest_debit:
            highest_debit = passbook_entry.debit_ug
            highest_member = member.name

    net_balance = round(total_budget - total_debit, 2)

    return FamilyPassbookResult(
        family_id=profile.id,
        family_name=profile.name,
        entries=entries,
        total_budget_ug=round(total_budget, 2),
        total_debit_ug=round(total_debit, 2),
        net_balance_ug=net_balance,
        highest_debit_member=highest_member,
    )
