# DOMAIN.md — air-quality knowledge the code must embody

Policy: every constant used in code lives in `data/constants.v1.json` with `value`, `unit`, `range`,
`source`, `verified` (bool). Values marked `"verified": false` MUST be checked against the cited source
during ticket FND-02 (using the official sources), then flipped to true with the exact page/table cited. Never invent a
source. If you cannot verify, keep the value, keep `verified: false`, and surface the range in the UI.

## Pollutants
- **PM2.5** (fine particles ≤ 2.5 µm) is the primary metric for dose and budget: penetrates deep into lungs,
  infiltrates indoors. **PM10** shown for context. Google returns concentrations in µg/m³ for particulates.
- India's **National AQI (CPCB)** PM2.5 24-h breakpoints: Good 0–30, Satisfactory 31–60, Moderate 61–90,
  Poor 91–120, Very Poor 121–250, Severe > 250 µg/m³. AQI categories: Good 0–50, Satisfactory 51–100,
  Moderate 101–200, Poor 201–300, Very Poor 301–400, Severe 401–500.
- **WHO 2021 Air Quality Guideline:** PM2.5 24-h mean 15 µg/m³; annual 5 µg/m³. This defines the air budget.

## Winter smog mechanics (why timing matters)
- Winter nights and early mornings: low mixing height / temperature inversion traps pollutants near the
  ground → early-morning and late-evening peaks; early-to-mid afternoon is usually the cleanest window.
  The planner must NOT hardcode this — it reads the forecast; the narrator may explain it.
- North India seasonal drivers: post-harvest crop-residue burning (roughly Oct–Nov), festive fireworks,
  vehicle traffic, construction dust, biomass/coal heating, low wind.
- Delhi NCR operates the **Graded Response Action Plan (GRAP)** with stages keyed to AQI
  (Stage I Poor, II Very Poor, III Severe, IV Severe+). Show GRAP context only for NCR coordinates; verify
  current stage thresholds at kickoff (`verified:false` until checked).

## Dose and budget
- Inhaled dose (µg) = Σ_hours concentration (µg/m³) × inhalation rate (m³/h) × hours.
- Inhalation rate depends on age band and activity level (EPA Exposure Factors Handbook, Ch. 6). Children
  inhale more air per kg body weight than adults — the passbook must show this, it is the emotional core.
- Air budget (µg/day) = WHO 24-h guideline (15 µg/m³) × member's daily inhalation volume (m³/day).
- Cigarette equivalence (Berkeley Earth approximation): ~22 µg/m³ PM2.5 over 24 h ≈ 1 cigarette/day.
  Label it "rough equivalence" everywhere.

## Indoor air (single-zone mass balance)
dC/dt = P·a·C_out − (a + k + CADR/V)·C + S/V
- P penetration factor, a air-exchange rate (1/h; windows closed vs open), k deposition rate (1/h),
  CADR clean-air delivery rate (m³/h), V room volume (m³), S indoor source strength (µg/h).
- Exact step solution for constant inputs over Δt: C(t+Δt) = C_ss + (C(t) − C_ss)·e^(−λΔt),
  λ = a + k + CADR/V, C_ss = (P·a·C_out + S/V)/λ.
- Purifier sizing heuristic: CADR ≥ V × target effective ACH (commonly 4–5 /h for smoggy conditions).
- Indoor sources to model: frying/tadka, incense (agarbatti), mosquito coils, candles, angithi/coal or wood
  heating, smoking, kerosene. Source strengths are highly uncertain → ranges required.
- "Air the house" only when C_out < C_in, and prefer the forecast's cleanest hour.

## Mitigation hierarchy (narrator should follow this order)
1. Remove/avoid sources (no coils/incense on severe days, lid-on cooking, exhaust fan, no indoor burning).
2. Time-shift outdoor exposure to cleaner hours; reduce exertion outdoors on severe days.
3. Seal and filter (keep windows closed in peaks, run purifier in the room where people sleep).
4. Personal protection: well-fitted N95/FFP2 outdoors on Poor+ days (fit matters more than brand).
5. Community: carpools, no leaf/garbage burning, report open burning.

## Health boundary (hard rule)
Exposure reduction advice only. No diagnosis, no medication or dosing advice. Red-flag symptoms
(breathlessness at rest, chest pain, bluish lips, confusion, child struggling to breathe) → "seek medical
care now" message first, everything else after. Sensitive-group advice may use Google's health
recommendations (children, elderly, pregnant, lung disease, heart disease, athletes).

## Emissions (what the household adds)
Per activity unit: kg CO₂ and g PM2.5 (e.g., per km by mode, per hour of angithi, per hour of generator,
per kg of leaves burned). These factors are uncertain → each has a range and source; the UI shows ranges.
Community scaling is linear: households × participation × per-household delta.
