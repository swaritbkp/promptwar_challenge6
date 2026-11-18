# PRD — HawaKhata (Air Passbook)

## Problem statement → feature map (this table goes into README.md too)
| Brief clause | Feature | Proof in code |
|---|---|---|
| GenAI-powered assistant | F5 Ask HawaKhata (multi-turn, tool-calling) | `agent/agent.py: build_agent()`, `agent/tools.py` |
| helps families | Per-member passbook with age/activity-specific breathing rates and sensitivities | `engine/dose.py: compute_member_dose()` |
| …and communities | Mohalla multiplier for collective impact | `engine/swaps.py: scale_to_community()` |
| severe winter smog | NAQI bands, inversion-hour awareness, severe-day alerting | `engine/aqi.py`, `services/brief_service.py` |
| low-emission daily routines | F2 Clean-Window Planner | `engine/planner.py: optimise_day_plan()` |
| indoor air quality hacks | F3 Indoor Air Simulator | `engine/indoor_model.py: simulate_indoor_pm25()` |
| sustainable alternatives | F4 Swap Simulator | `engine/emissions.py`, `engine/swaps.py: evaluate_swap()` |
| tailored to location | Google Air Quality API (forecast + local index + health recs) | `integrations/air_quality.py` |
| …and lifestyle | Family profile: members, home, commute, heating, cooking, purifier | `api/schemas.py: FamilyProfile` |
| clearly explaining the direct impact | Debit/Savings/Emissions/Balance + "Why this number?" + How it works page | `engine/budget.py`, `services/passbook_service.py: explain_number()` |

## Personas (fixtures only — never referenced in logic)
1. **Mehra family, Gurugram (hero demo):** parents 38 and 36 (office, car commute), daughter 7 (school
   7:30–13:30, asthma flagged by parent), grandmother 68 (morning walk habit). Purifier in one bedroom.
2. **Sandhu family, Mohali (origin story):** joint family of 6, scooter commute, angithi in the evening,
   evening walk, no purifier.

## Family profile (user enters once, stored in browser localStorage only)
- Location (lat/lng or city search), language (en/hi; pa in P1).
- Members: label (not real name required), age band, sensitivities (child, elderly, pregnant, lung/heart
  condition — optional, never sent to Gemini unless the user includes it in chat), daily schedule blocks.
- Home: rooms (volume m³ derived from area × height), window habit, purifier (CADR m³/h, room), cooking
  style (frying / tadka frequency), incense, mosquito coil, heating (angithi/coal, wood, electric, none),
  smoking indoors.
- Mobility: commute mode, distance, days/week; generator use.

## Features & acceptance criteria
### F1 Family Air Passbook
- For a date, per member: `debit_ug`, `budget_ug`, `balance_ug`, `overspend_ratio`, `cigarette_equivalent`,
  hour-by-hour exposure timeline (location: indoor/outdoor/transit), top 3 exposure contributors.
- AC: debit ≥ 0; budget scales with breathing volume; changing outdoor PM2.5 ×k (indoor model linear)
  scales debit ×k; every figure has an `explanation` object (formula, inputs, constant ids, sources).

### F2 Clean-Window Planner
- Inputs: fixed blocks (school/office), flexible activities (walk 45 min between 06:00–20:00, errands,
  airing the house, kids' outdoor play), forecast series with uncertainty.
- Output: chosen start times, per-member savings vs the user's usual schedule, and a robust choice that
  minimises expected dose + λ·P90 dose (Monte Carlo, seeded RNG).
- AC: never moves a fixed block; never overlaps activities of the same member; deterministic given seed;
  savings ≥ 0 (if usual schedule is already optimal, says so).

### F3 Indoor Air Simulator
- Single-zone mass balance per room, hourly step, exact exponential solution per step.
- Interventions: windows open/closed hours, purifier on/off + CADR, cooking/incense/coil events, heating.
- AC: monotonic — more CADR never raises indoor PM; adding a source never lowers it; steady state matches
  closed-form; "air the house" recommendation only when outdoor < indoor.

### F4 Swap Simulator + Mohalla multiplier
- Catalogue of swaps from `data/constants.v1.json` (car→metro, car→carpool, angithi→electric heater + layers,
  burning leaves→composting, incense→none, coil→net/repellent, generator→inverter, frying→steaming on
  severe days, open-window cooking→exhaust).
- Output per swap: Δ breathe (µg, per member) and Δ emit (g PM2.5, kg CO₂) per day/week/month, plus
  community scaling: households × participation.
- AC: deltas sign-correct; scaling linear; every factor cited with uncertainty range.

### F5 Ask HawaKhata (agent)
- Multi-turn chat with session memory (bounded), tool calling over services, clarifying follow-ups when
  the profile is missing data needed to answer, answers in the user's language (en/hi).
- AC: every number in an answer is grounded; injection attempts refused; symptom red flags → seek care
  now; no diagnosis, no medicine dosing; works in fallback mode without Gemini.

### F6 Proactive Smog Brief
- Morning brief: today's worst/cleanest hours, alerts per sensitive member, top 3 actions, and
  "what changed since yesterday". Re-plan automatically when forecast at a planned slot moves by more
  than the configured threshold.
- AC: triggers are data-driven thresholds (config), never hardcoded per city.

### F7 Story mode
- `/?story=ncr` (Delhi NCR) and `/?story=chd` (Chandigarh): loads the demo profile, fixture air data and a
  fixed clock from `data/story.v1.json`, then walks 8 steps with captions (EN/HI), keyboard controls and
  highlighted targets. All numbers come from the normal endpoints.
- AC: identical numbers on repeated runs; fully keyboard-operable; captions announced to screen readers;
  works with no API keys.

### F8 Onboarding + How it works
- Onboarding per `docs/UX_SPEC.md` (3 steps, ≤ 60 s, skippable, "try a demo family").
- How it works page: architecture diagram (inline SVG), Google services, "every number is computed",
  constants & sources table generated from `data/constants.v1.json`, privacy statement.
- AC: page content generated from data/config (no duplicated numbers); passes accessibility tests.

## Goals (outcomes, not features)
- A parent understands, in under a minute, how much fine dust each family member breathed today and why.
- The family gets at least one concrete change for today that measurably lowers a member's debit.
- A neighbourhood group can see the collective effect of a shared change.

## Non-goals (this build)
Accounts, server-side storage, medical advice, live sensor/IoT data, maps, notifications/push, native
apps, Punjabi (P1), routing (P1).

## How we'll know it worked
- First insight ≤ 60 s for a new user (measured in story/onboarding walkthroughs).
- Every displayed number traceable to a formula + source (grounding pass-rate 100 % in eval).
- At least one move with a positive saving for both demo families on the fixture day.

## Assumptions & constraints
Assumptions: Google's forecast is a reasonable proxy for neighbourhood PM2.5; indoor single-zone model
is good enough to rank actions (values shown with ranges). Constraints: one-day build, Gemini on
Antigravity, Cloud Run free/low tier, no personal data stored server-side.

## Unknowns (resolved during FND tickets — write "Unknown" rather than guess)
| Question | Resolved by |
|---|---|
| India local AQI code returned by the Air Quality API | FND-01 |
| Emission factors and indoor source strengths for Indian households | FND-02 |

## Non-functional
- p95 API latency < 1.5 s in fallback mode, < 6 s with Gemini; Google AQ responses cached per ~1 km cell.
- Works offline-from-keys (fixtures). WCAG 2.2 AA. No personal data leaves the device except the minimum
  needed per request; nothing persisted server-side.
