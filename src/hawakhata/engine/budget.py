"""Family Air Passbook — debit, budget, balance, and exposure equivalents.

The air budget defines the maximum daily PM2.5 mass a person can inhale while
remaining within the WHO 2021 24-hour guideline (15 ug/m3).
    budget_ug = WHO_24h_guideline (15 ug/m3) * DailyInhalationVolume (m3/day)
    balance_ug = budget_ug - debit_ug
    overspend_ratio = debit_ug / budget_ug
"""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.dose import DoseContributor
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class PassbookEntry:
    """Passbook ledger line item for a single family member."""

    member_label: str
    age_band: str
    budget_ug: float
    debit_ug: float
    balance_ug: float
    overspend_ratio: float
    is_over_budget: bool
    cigarette_equivalent: float
    cigarette_label: str
    hourly_doses_ug: list[float]
    top_contributors: list[DoseContributor]
    explanation: Explanation


def daily_air_budget_ug(age_band: str) -> float:
    """Calculate the personal WHO-based daily permissible PM2.5 inhalation budget.

    Formula:
        budget_ug = WHO_24h_AQG (15 ug/m3) * Daily_Mean_Inhalation_Volume (m3/day)

    Args:
        age_band: Age group identifier (e.g. '0_1', '6_11', '31_41', '71_81').

    Returns:
        Daily budget in micrograms of PM2.5.
    """
    who_guideline = float(get_constant("who_aqg_pm25_24h").value)
    daily_means = get_constant("inhalation_rate_daily_mean").value
    daily_volume_m3 = float(daily_means.get(age_band, 16.0))
    return who_guideline * daily_volume_m3


def build_passbook_entry(
    member_label: str,
    age_band: str,
    debit_ug: float,
    hourly_doses_ug: list[float] | None = None,
    top_contributors: list[DoseContributor] | None = None,
) -> PassbookEntry:
    """Build a complete passbook entry comparing inhaled debit against air budget.

    Args:
        member_label: Display name or label for the member.
        age_band: Age bracket key.
        debit_ug: Total inhaled PM2.5 mass in micrograms.
        hourly_doses_ug: Optional 24-hour hourly dose breakdown.
        top_contributors: Optional top contributors list.

    Returns:
        PassbookEntry object with balance, overspend ratio, cigarette equivalence, and explanation.
    """
    budget = daily_air_budget_ug(age_band)
    balance = budget - debit_ug
    overspend = (debit_ug / budget) if budget > 0 else 0.0

    # Berkeley Earth cigarette equivalence:
    # 22 ug/m3 24h average PM2.5 exposure corresponds roughly to 1 cigarette per day.
    # Mean concentration = total_debit_ug / daily_volume_m3
    daily_means = get_constant("inhalation_rate_daily_mean").value
    daily_volume_m3 = float(daily_means.get(age_band, 16.0))
    mean_24h_exposure_ug_m3 = (debit_ug / daily_volume_m3) if daily_volume_m3 > 0 else 0.0
    equiv_factor = float(get_constant("cigarette_equiv_pm25_24h").value)
    cigarette_count = (mean_24h_exposure_ug_m3 / equiv_factor) if equiv_factor > 0 else 0.0

    exp = Explanation(
        formula="budget = WHO_24h(15 ug/m3) * DailyIR(m3); balance = budget - debit; "
        "overspend = debit / budget; cig_equiv = (debit / DailyIR) / 22 ug/m3",
        inputs={
            "member": member_label,
            "age_band": age_band,
            "debit_ug": f"{debit_ug:.1f} ug",
            "budget_ug": f"{budget:.1f} ug",
            "balance_ug": f"{balance:.1f} ug",
            "overspend_ratio": f"{overspend:.2f}x",
            "cigarette_equiv": f"{cigarette_count:.1f}",
        },
        constants_used=[
            "who_aqg_pm25_24h",
            "inhalation_rate_daily_mean",
            "cigarette_equiv_pm25_24h",
        ],
        sources=[
            "WHO Global Air Quality Guidelines (2021) 24-hour PM2.5 guideline level (15 ug/m3)",
            "US EPA Exposure Factors Handbook (2011) Chapter 6",
            "Berkeley Earth (Muller & Muller 2015) rough cigarette equivalence model",
        ],
        assumptions=[
            "Linear proportionality between inhalation dose and ambient particulate exposure",
            "Rough equivalence label applies to all cigarette comparisons",
        ],
    )

    return PassbookEntry(
        member_label=member_label,
        age_band=age_band,
        budget_ug=budget,
        debit_ug=debit_ug,
        balance_ug=balance,
        overspend_ratio=overspend,
        is_over_budget=debit_ug > budget,
        cigarette_equivalent=cigarette_count,
        cigarette_label="Rough equivalence (Berkeley Earth model)",
        hourly_doses_ug=hourly_doses_ug or [],
        top_contributors=top_contributors or [],
        explanation=exp,
    )
