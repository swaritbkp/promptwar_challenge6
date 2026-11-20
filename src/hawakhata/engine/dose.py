"""Personal inhaled PM2.5 dose calculations."""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class ScheduleBlock:
    """An activity window entered by the user or preset in a demo profile."""

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
    aliases = {
        "child": "6_11",
        "teen": "11_16",
        "adult": "31_41",
        "senior": "61_71",
        "elder": "61_71",
    }
    band = aliases.get(age_band.lower(), age_band)
    daily_means = get_constant("inhalation_rate_daily_mean").value
    multipliers = get_constant("activity_multiplier").value
    mean_daily = float(daily_means.get(band, 16.0))
    m_default = (
        "moderate"
        if activity in ("run", "play", "pet_walk")
        else (
            "light"
            if activity in ("walk", "school_run", "market_shopping", "park_terrace")
            else "sedentary"
        )
    )
    mult = float(multipliers.get(activity, multipliers.get(m_default, 1.0)))
    return (mean_daily / 24.0) * mult


def build_member_timeline(schedule_blocks: list[ScheduleBlock] | None = None) -> list[TimelineSlot]:
    """Construct a full 24-hour member timeline applying sensible defaults for unassigned hours."""
    timeline = [
        TimelineSlot(
            hour=h,
            micro_env="indoor_home",
            activity="sleep" if h in (22, 23, 0, 1, 2, 3, 4, 5) else "sedentary",
            label="Sleep" if h in (22, 23, 0, 1, 2, 3, 4, 5) else "Home / Rest",
        )
        for h in range(24)
    ]
    if schedule_blocks:
        for b in schedule_blocks:
            for h in range(max(0, b.start_hour), min(24, b.end_hour)):
                timeline[h] = TimelineSlot(h, b.micro_env, b.activity, b.label or b.micro_env)
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

    concs: list[float] = []
    doses: list[float] = []
    num_hours = min(len(timeline), len(outdoor_pm25_series), 24)

    for h in range(num_hours):
        slot = timeline[h]
        c_out = max(0.0, outdoor_pm25_series[h])
        if slot.micro_env == "indoor_home":
            c_eff = (
                max(0.0, indoor_home_series[h])
                if (indoor_home_series and h < len(indoor_home_series))
                else c_out * infiltration_closed
            )
        elif slot.micro_env == "indoor_other":
            c_eff = c_out * infiltration_closed
        elif slot.micro_env in ("outdoor", "transit_walk_cycle", "park_terrace", "terrace"):
            c_eff = c_out
        else:
            c_eff = c_out * float(in_vehicle_ratios.get(slot.micro_env, 1.0))
        concs.append(c_eff)
        doses.append(c_eff * inhalation_rate_m3_per_h(age_band, slot.activity) * 1.0)

    tot = sum(doses)
    contributors = [
        DoseContributor(
            hour=h,
            micro_env=timeline[h].micro_env,
            activity=timeline[h].activity,
            dose_ug=round(doses[h], 2),
            share_percent=round((doses[h] / tot * 100.0) if tot > 0 else 0.0, 1),
        )
        for h in range(num_hours)
    ]
    contributors.sort(key=lambda x: x.dose_ug, reverse=True)

    exp = Explanation(
        formula="dose_ug = sum(C_micro(t) * InhalationRate(age, activity) * 1h)",
        inputs={
            "age_band": age_band,
            "total_dose_ug": f"{tot:.1f} ug",
            "mean_concentration": f"{(sum(concs) / max(1, num_hours)):.1f} ug/m3",
        },
        constants_used=[
            "inhalation_rate_daily_mean",
            "activity_multiplier",
            "in_vehicle_ratio",
            "infiltration_closed_building",
        ],
        sources=["US EPA Exposure Factors Handbook (2011)", "Goel & Kumar (2015)"],
        assumptions=[
            "Uniform 1-hour time slices",
            "Constant micro-environmental concentrations per hour",
        ],
    )
    return MemberDoseResult(
        total_dose_ug=tot,
        hourly_doses_ug=doses,
        hourly_concentrations_ug_m3=concs,
        top_contributors=contributors[:3],
        explanation=exp,
    )


MASK_TYPES: tuple[str, ...] = ("none", "surgical", "n95")


@dataclass(frozen=True, slots=True)
class MaskedActivityDose:
    """Inhaled dose for one outdoor activity with and without a face mask."""

    mask: str
    filtration_factor: float
    mean_outdoor_pm25: float
    inhalation_rate_m3_per_h: float
    duration_min: int
    unmasked_dose_ug: float
    masked_dose_ug: float
    mask_saved_ug: float
    budget_ug: float
    budget_share_pct: float
    within_budget: bool
    explanation: Explanation


def mask_filtration_factor(mask: str) -> float:
    """Return the fraction of ambient PM2.5 still inhaled through a mask (1.0 = no mask)."""
    factors = get_constant("mask_filtration_factor").value
    if mask not in factors:
        raise KeyError(f"Unknown mask type: '{mask}'")
    return float(factors[mask])


def compute_masked_activity_dose(
    age_band: str,
    activity: str,
    window_pm25: list[float],
    duration_min: int,
    mask: str,
    budget_ug: float,
) -> MaskedActivityDose:
    """Compute an outdoor activity's inhaled dose under a mask, versus the member's WHO budget.

    dose = mean(C_out over window) x IR(age, activity) x hours x mask_factor.
    """
    factor = mask_filtration_factor(mask)
    mean_pm = sum(max(0.0, p) for p in window_pm25) / max(1, len(window_pm25))
    ir = inhalation_rate_m3_per_h(age_band, activity)
    hours = max(0, duration_min) / 60.0
    unmasked = mean_pm * ir * hours
    masked = unmasked * factor
    share = (masked / budget_ug * 100.0) if budget_ug > 0 else 0.0
    return MaskedActivityDose(
        mask=mask,
        filtration_factor=factor,
        mean_outdoor_pm25=round(mean_pm, 1),
        inhalation_rate_m3_per_h=round(ir, 3),
        duration_min=duration_min,
        unmasked_dose_ug=round(unmasked, 1),
        masked_dose_ug=round(masked, 1),
        mask_saved_ug=round(unmasked - masked, 1),
        budget_ug=round(budget_ug, 1),
        budget_share_pct=round(share, 1),
        within_budget=masked <= budget_ug,
        explanation=Explanation(
            formula="dose_ug = mean(C_out) * IR(age, activity) * hours * mask_factor",
            inputs={
                "mean_outdoor_pm25": f"{mean_pm:.1f} ug/m3",
                "inhalation_rate": f"{ir:.3f} m3/h",
                "hours": f"{hours:.2f} h",
                "mask_factor": f"{factor:.2f}",
            },
            constants_used=["mask_filtration_factor", "inhalation_rate_daily_mean"],
            sources=["Cherrie et al. (2018) real-world mask leakage", "US EPA EFH (2011)"],
            assumptions=["Mask worn for the whole activity", "Fit-adjusted, not lab efficiency"],
        ),
    )
