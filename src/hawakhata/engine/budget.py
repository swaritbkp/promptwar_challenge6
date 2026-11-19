"""Family Air Passbook — debit, budget, balance, and exposure equivalents."""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.dose import DoseContributor
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class PassbookEntry:
    """Passbook ledger line item for a single family member."""

    member_id: str
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
    """Calculate the personal WHO-based daily permissible PM2.5 inhalation budget."""
    aliases = {
        "child": "6_11",
        "teen": "11_16",
        "adult": "31_41",
        "senior": "61_71",
        "elder": "61_71",
    }
    band = aliases.get(age_band.lower(), age_band)
    who_guideline = float(get_constant("who_aqg_pm25_24h").value)
    daily_means = get_constant("inhalation_rate_daily_mean").value
    return who_guideline * float(daily_means.get(band, 16.0))


def build_passbook_entry(
    member_id: str,
    member_label: str,
    age_band: str,
    debit_ug: float,
    hourly_doses_ug: list[float] | None = None,
    top_contributors: list[DoseContributor] | None = None,
) -> PassbookEntry:
    """Build a complete passbook entry comparing inhaled debit against air budget."""
    budget = daily_air_budget_ug(age_band)
    balance = budget - debit_ug
    overspend = (debit_ug / budget) if budget > 0 else 0.0

    daily_means = get_constant("inhalation_rate_daily_mean").value
    daily_volume_m3 = float(daily_means.get(age_band, 16.0))
    mean_24h_exposure = (debit_ug / daily_volume_m3) if daily_volume_m3 > 0 else 0.0
    equiv_factor = float(get_constant("cigarette_equiv_pm25_24h").value)
    cigs = (mean_24h_exposure / equiv_factor) if equiv_factor > 0 else 0.0

    exp = Explanation(
        formula="budget = WHO_24h(15 ug/m3) * DailyIR(m3); balance = budget - debit; overspend = debit / budget; cig_equiv = (debit / DailyIR) / 22 ug/m3",
        inputs={
            "member": member_label,
            "age_band": age_band,
            "debit_ug": f"{debit_ug:.1f} ug",
            "budget_ug": f"{budget:.1f} ug",
            "balance_ug": f"{balance:.1f} ug",
            "overspend_ratio": f"{overspend:.2f}x",
            "cigarette_equiv": f"{cigs:.1f}",
        },
        constants_used=[
            "who_aqg_pm25_24h",
            "inhalation_rate_daily_mean",
            "cigarette_equiv_pm25_24h",
        ],
        sources=[
            "WHO Global Air Quality Guidelines (2021)",
            "US EPA Exposure Factors Handbook (2011)",
            "Berkeley Earth (2015)",
        ],
        assumptions=["Linear dose proportionality", "Rough equivalence label"],
    )

    return PassbookEntry(
        member_id=member_id,
        member_label=member_label,
        age_band=age_band,
        budget_ug=budget,
        debit_ug=debit_ug,
        balance_ug=balance,
        overspend_ratio=overspend,
        is_over_budget=balance < 0,
        cigarette_equivalent=cigs,
        cigarette_label="Rough equivalence (Berkeley Earth model)",
        hourly_doses_ug=hourly_doses_ug or [],
        top_contributors=top_contributors or [],
        explanation=exp,
    )
