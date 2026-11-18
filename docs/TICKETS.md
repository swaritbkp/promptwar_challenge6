# Feature tickets — HawaKhata

One ticket = one piece of work that can be built and checked in one session. Build strictly in backlog
order, one at a time. A ticket is **Done** only when every acceptance criterion (AC) and the Definition
of Done below are met. Security rule numbers (R#) refer to `docs/SECURITY.md` §8.

## Definition of Done (every ticket)
1. `python scripts/gate.py` is GREEN (lint, format, strict types, tests + coverage, repo audit).
2. Every AC is met — not "close enough" — and each AC has at least one automated test.
3. At least one edge case was exercised by hand (command or browser) and written in the ticket report.
4. Only files needed by this ticket changed; nothing beyond the ticket was added.
5. The R# rules listed on the ticket are met; no secrets committed.
6. Status updated here and in the progress log; committed with a conventional message.

## Backlog
| ID | Title | Depends on | Pri | Status |
|---|---|---|---|---|
| FND-00 | Keep the tested scaffold green (config, core, gate, audit) | — | Must | Done |
| FND-01 | Verify external APIs and pin dependencies | FND-00 | Must | Done |
| FND-02 | Verify and complete the constants file with sources | FND-01 | Must | Done |
| FND-03 | Create Delhi NCR and Chandigarh air-data fixtures | FND-01 | Must | Done |
| ENG-01 | Load constants and define the Explanation value object | FND-02 | Must | Done |
| ENG-02 | Map PM2.5 and AQI to India NAQI categories | ENG-01 | Must | Done |
| ENG-03 | Compute per-member inhaled dose from a day timeline | ENG-01 | Must | Done |
| ENG-04 | Compute the daily air budget and passbook entry | ENG-03 | Must | Done |
| ENG-05 | Simulate indoor PM2.5 with the mass-balance model | ENG-01 | Must | Done |
| ENG-06 | Rank indoor hacks, ventilation hours, purifier sizing | ENG-05 | Must | Done |
| ENG-07 | Sample forecast uncertainty (seeded) | ENG-01 | Must | Done |
| ENG-08 | Optimise the day plan (robust clean windows) | ENG-03, ENG-07 | Must | Done |
| ENG-09 | Compute emissions, swap deltas and community scaling | ENG-03, ENG-05 | Must | Done |
| INT-01 | Google Air Quality client with cache, breaker, fixture fallback | FND-03 | Must | Done |
| API-01 | Request/response schemas and envelope | ENG-04 | Must | Done |
| API-02 | Passbook endpoint | API-01, INT-01 | Must | Done |
| API-03 | Plan endpoint | API-02, ENG-08 | Must | Done |
| API-04 | Indoor simulate endpoint | API-02, ENG-06 | Must | Done |
| API-05 | Swaps impact endpoint | API-02, ENG-09 | Must | Done |
| API-06 | Brief endpoint with forecast-shift re-plan | API-03 | Must | Done |
| API-07 | Demo profiles and story endpoints | API-02 | Must | Done |
| AGT-01 | Input/output guardrails | API-01 | Must | Done |
| AGT-02 | Numeric grounding gate | AGT-01 | Must | Done |
| AGT-03 | Versioned prompt registry | — | Must | Done |
| AGT-04 | Gemini client: cascade, timeouts, AI quota | AGT-03 | Must | Done |
| AGT-05 | ADK agent with tools, sessions and follow-ups | AGT-02, AGT-04, API-06 | Must | Done |
| AGT-06 | Deterministic fallback router and composer | AGT-05 | Must | Done |
| AGT-07 | Chat endpoint | AGT-06 | Must | Not started |
| AGT-08 | Evaluation harness | AGT-07 | Must | Not started |
| UI-00 | Design screens in Stitch | — | Must | Not started |
| UI-01 | Design tokens, base layout, navigation, icons, i18n | UI-00, API-07 | Must | Not started |
| UI-02 | Onboarding (≤ 60 s) | UI-01 | Must | Not started |
| UI-03 | Today screen | UI-02, API-06 | Must | Not started |
| UI-04 | Plan screen | UI-03 | Must | Not started |
| UI-05 | Home air screen | UI-03 | Must | Not started |
| UI-06 | Swaps + Mohalla screen | UI-03 | Must | Not started |
| UI-07 | Ask sheet with AI states | UI-03, AGT-07 | Must | Not started |
| UI-08 | How it works page | UI-01 | Must | Not started |
| UI-09 | Story mode | UI-03..UI-08 | Must | Not started |
| HRD-01 | Security audit with proof files | all above | Must | Not started |
| HRD-02 | Accessibility audit | all UI | Must | Not started |
| REL-01 | README with Code Map | HRD-01 | Must | Not started |
| REL-02 | Deploy to Cloud Run | REL-01 | Must | Not started |
| REL-03 | Early release + score-driven improvement rounds | REL-02 | Must | Not started |
| REL-04 | Demo lock and video assets | REL-02 | Must | Not started |

## Parked
| Idea | Found during | Why parked |
|---|---|---|
