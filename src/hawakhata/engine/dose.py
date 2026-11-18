"""Compute personal inhaled fine particulate (PM2.5) dose across daily activities.

Implements the micro-environmental exposure model:
    dose_ug = sum(C_micro(t) * InhalationRate(age, activity) * dt)
with age-stratified physiological ventilation rates from US EPA (2011).
"""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class ScheduleBlock:
    """An activity window entered by the user or preset in a demo profile.

    Attributes:
        start_hour: Beginning of activity (0..23).
        end_hour: End of activity (1..24).
        micro_env: Environment identifier (e.g. 'indoor_home', 'outdoor', 'transit_car').
        activity: Physical exertion level ('sleep', 'sedentary', 'light', 'moderate', 'vigorous').
        label: User-facing descriptive name.
    """

    start_hour: int
    end_hour: int
    micro_env: str
    activity: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class TimelineSlot:
    """A discretized 1-hour member schedule slice."""

    hour: int
    micro_env: str
    activity: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class DoseContributor:
    """Top exposure contribution period."""

    hour: int
    micro_env: str
    activity: str
    dose_ug: float
    share_percent: float


@dataclass(frozen=True, slots=True)
class MemberDoseResult:
    """Computed inhaled dose outcome for a single family member over 24 hours."""

    total_dose_ug: float
    hourly_doses_ug: list[float]
    hourly_concentrations_ug_m3: list[float]
    top_contributors: list[DoseContributor]
    explanation: Explanation


def inhalation_rate_m3_per_h(age_band: str, activity: str) -> float:
    """Calculate hourly air breathing volume based on age band and exertion level."""
    daily_means = get_constant("inhalation_rate_daily_mean").value
    multipliers = get_constant("activity_multiplier").value

    mean_daily_m3 = float(daily_means.get(age_band, 16.0))
    mult = float(multipliers.get(activity, 1.0))
    return (mean_daily_m3 / 24.0) * mult


def build_member_timeline(
    schedule_blocks: list[ScheduleBlock] | None = None,
) -> list[TimelineSlot]:
    """Construct a full 24-hour member timeline applying sensible defaults for unassigned hours."""
    timeline: list[TimelineSlot] = []

    for h in range(24):
        # Default schedule
        if h in (22, 23, 0, 1, 2, 3, 4, 5):
            env = "indoor_home"
            act = "sleep"
            label = "Sleep"
        else:
            env = "indoor_home"
            act = "sedentary"
            label = "Home / Rest"
        timeline.append(TimelineSlot(hour=h, micro_env=env, activity=act, label=label))

    if schedule_blocks:
        for block in schedule_blocks:
            for h in range(max(0, block.start_hour), min(24, block.end_hour)):
                timeline[h] = TimelineSlot(
                    hour=h,
                    micro_env=block.micro_env,
                    activity=block.activity,
                    label=block.label or block.micro_env,
                )

    return timeline


def compute_member_dose(
    age_band: str,
    timeline: list[TimelineSlot],
    outdoor_pm25_series: list[float],
    indoor_home_series: list[float] | None = None,
) -> MemberDoseResult:
    """Calculate personal inhaled PM2.5 dose across a 24-hour timeline."""
    in_vehicle_ratios = get_constant("in_vehicle_ratio").value
    infiltration_closed = float(get_constant("infiltration_closed_building").value)

    hourly_concentrations: list[float] = []
    hourly_doses: list[float] = []

    num_hours = min(len(timeline), len(outdoor_pm25_series), 24)

    for h in range(num_hours):
        slot = timeline[h]
        c_out = max(0.0, outdoor_pm25_series[h])

        # Determine effective concentration for micro-environment
        if slot.micro_env == "indoor_home":
            if indoor_home_series and h < len(indoor_home_series):
                c_eff = max(0.0, indoor_home_series[h])
            else:
                c_eff = c_out * infiltration_closed
        elif slot.micro_env == "indoor_other":
            c_eff = c_out * infiltration_closed
        elif slot.micro_env in ("outdoor", "transit_walk_cycle"):
            c_eff = c_out
        else:
            # Transit modes: car, two_wheeler, bus, metro
            ratio = float(in_vehicle_ratios.get(slot.micro_env, 1.0))
            c_eff = c_out * ratio

        hourly_concentrations.append(c_eff)
        ir = inhalation_rate_m3_per_h(age_band, slot.activity)
        dose = c_eff * ir * 1.0  # 1 hour duration
        hourly_doses.append(dose)

    total_dose = sum(hourly_doses)

    # Compute top 3 contributors
    contributors: list[DoseContributor] = []
    for h in range(num_hours):
        d = hourly_doses[h]
        share = (d / total_dose * 100.0) if total_dose > 0 else 0.0
        contributors.append(
            DoseContributor(
                hour=h,
                micro_env=timeline[h].micro_env,
                activity=timeline[h].activity,
                dose_ug=round(d, 2),
                share_percent=round(share, 1),
            )
        )

    contributors.sort(key=lambda x: x.dose_ug, reverse=True)
    top_3 = contributors[:3]

    exp = Explanation(
        formula="dose_ug = sum(C_micro(t) * InhalationRate(age, activity) * 1h)",
        inputs={
            "age_band": age_band,
            "total_dose_ug": f"{total_dose:.1f} ug",
            "mean_concentration": f"{(sum(hourly_concentrations) / max(1, num_hours)):.1f} ug/m3",
        },
        constants_used=[
            "inhalation_rate_daily_mean",
            "activity_multiplier",
            "in_vehicle_ratio",
            "infiltration_closed_building",
        ],
        sources=[
            "US EPA Exposure Factors Handbook (2011), Table 6-1 & 6-2",
            "Goel & Kumar (2015) Atmospheric Environment commuter exposure in Delhi",
        ],
        assumptions=[
            "Uniform 1-hour time slices",
            "Constant micro-environmental concentrations during each hourly interval",
        ],
    )

    return MemberDoseResult(
        total_dose_ug=total_dose,
        hourly_doses_ug=hourly_doses,
        hourly_concentrations_ug_m3=hourly_concentrations,
        top_contributors=top_3,
        explanation=exp,
    )
