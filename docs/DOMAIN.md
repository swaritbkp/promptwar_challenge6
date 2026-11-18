# DOMAIN.md — Air-Quality Knowledge Base

All numerical constants live in `data/constants.v1.json` with value, unit, range, source, and verification status.

## Pollutants & NAQI Breakpoints
- **PM2.5:** Primary metric for inhaled dose and budget (fine particles ≤ 2.5 µm).
- **India NAQI (CPCB) 24h breakpoints (µg/m³):** Good 0–30, Satisfactory 31–60, Moderate 61–90, Poor 91–120, Very Poor 121–250, Severe >250.
- **NAQI Index bands:** Good 0–50, Satisfactory 51–100, Moderate 101–200, Poor 201–300, Very Poor 301–400, Severe 401–500.
- **WHO 2021 Guidelines:** PM2.5 24h mean 15 µg/m³; annual mean 5 µg/m³. Defines daily air budget.

## Inversion & Diurnal Smog Mechanics
- Winter nights/early mornings: low planetary boundary layer mixing height traps pollutants near ground.
- Cleanest window: typically early-to-mid afternoon (12:00–16:00). Engine reads forecast dynamically.
- Regional drivers: post-harvest stubble burning (Oct–Nov), fireworks, vehicular exhaust, construction, biomass heating.
- NCR GRAP: Stages I (Poor), II (Very Poor), III (Severe), IV (Severe+).

## Dose, Budget & Equivalencies
- Inhaled dose (µg) = Σ concentration (µg/m³) × inhalation rate (m³/h) × duration (h).
- Inhalation rate: EPA Exposure Factors Handbook (Ch. 6) stratified by age and exertion. Children inhale more air per kg body weight.
- Air budget (µg/day) = WHO 24h guideline (15 µg/m³) × member's 24h breathing volume (m³/day).
- Berkeley Earth cigarette equivalence: ~22 µg/m³ over 24h ≈ 1 cigarette/day.

## Indoor Mass-Balance Model
- Governing ODE: `dC/dt = P*a*C_out - (a + k + CADR/V)*C + S/V`.
- Exact exponential step: `C(t+Δt) = C_ss + (C(t) - C_ss)*exp(-λΔt)` where `λ = a + k + CADR/V` and `C_ss = (P*a*C_out + S/V)/λ`.
- Purifier sizing heuristic: `CADR >= V * target_ACH` (target 4–5 /h in severe smog).
- Indoor sources: frying/tadka, agarbatti/incense, mosquito coils, angithi/coal, smoking.
- Natural ventilation: recommend airing only when `C_out < C_in` at cleanest forecast window.

## Mitigation Hierarchy & Health Boundary
1. Eliminate indoor emission sources (no coils/incense on severe days, exhaust fans).
2. Time-shift outdoor exposure to cleanest forecast windows; reduce exertion.
3. Filter & seal (run HEPA purifier in bedrooms, close windows during peaks).
4. Personal protection: well-fitted N95/FFP2 masks outdoors on Poor+ days.
5. Community: carpools, eliminate waste/leaf burning, reporting violations.
- **Health Boundary:** Exposure reduction only. Zero medical diagnosis or drug dosing. Red flags (breathlessness at rest, chest pain, cyanosis) immediately trigger medical emergency advice.

## Emissions & Mohalla Scaling
- Emission factors: kg CO₂ and g PM2.5 per activity unit (km travelled, hours heating, kg waste).
- Community impact = households × adoption_rate × per_household_delta (linear scaling).
