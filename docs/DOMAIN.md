# DOMAIN.md — Air-Quality Knowledge Base

All numerical constants live in `data/constants.v1.json` with source and verification.

## Pollutants & NAQI Breakpoints
- **PM2.5:** Primary metric for inhaled dose and budget (fine particles ≤ 2.5 µm).
- **India NAQI (CPCB) 24h breakpoints (µg/m³):** Good 0–30, Satisfactory 31–60, Moderate 61–90, Poor 91–120, Very Poor 121–250, Severe >250.
- **NAQI Index bands:** Good 0–50, Satisfactory 51–100, Moderate 101–200, Poor 201–300, Very Poor 301–400, Severe 401–500.
- **WHO 2021 Guidelines:** PM2.5 24h mean 15 µg/m³; annual 5 µg/m³. Defines daily air budget.

## Inversion & Smog Dynamics
- Winter boundary layer traps pollutants near ground.
- Cleanest window: typically early afternoon (12:00–16:00). Engine reads forecast dynamically.
- Regional drivers: stubble burning, vehicular exhaust, construction, biomass heating.
- NCR GRAP: Stages I (Poor), II (Very Poor), III (Severe), IV (Severe+).

## Dose, Budget & Equivalencies
- Inhaled dose (µg) = Σ C_i × IR_i × t_i.
- Inhalation rate: EPA Exposure Factors Handbook (Ch. 6) stratified by age/activity.
- Air budget (µg/day) = WHO 24h guideline (15 µg/m³) × breathing volume (m³/day).
- Berkeley Earth: ~22 µg/m³ PM2.5 over 24h ≈ 1 cigarette/day.

## Indoor Mass-Balance Model
- Governing ODE: `dC/dt = P*a*C_out - (a + k + CADR/V)*C + S/V`.
- Exponential step: `C(t+Δt) = C_ss + (C(t) - C_ss)*exp(-λΔt)`.
- Purifier sizing: `CADR >= V * target_ACH` (target 5 /h).
- Mitigation: Eliminate sources (incense/coils/angithi) → time-shift windows → HEPA air purifier → N95 outdoors.
- Health Boundary: Exposure reduction only. Zero diagnosis or drug dosing. Red flags trigger 112 emergency notice.
