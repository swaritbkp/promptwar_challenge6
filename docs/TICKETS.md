# Feature tickets — HawaKhata

Build strictly in backlog order. One ticket = one tested work unit.

## Definition of Done (every ticket)
1. `python scripts/gate.py` is GREEN (lint, format, strict types, tests + coverage, repo audit).
2. Every AC is met and tested. Edge case hand-run in ticket report.
3. Only ticket files changed. Security R# rules met. Conventional commit.

## Backlog
| ID | Title | Dep | Pri | Status |
|---|---|---|---|---|
| FND-00 | Tested scaffold green | — | Must | Done |
| FND-01 | External APIs & dependencies | FND-00 | Must | Done |
| FND-02 | Constants file with sources | FND-01 | Must | Done |
| FND-03 | Air-data fixtures (NCR, CHD) | FND-01 | Must | Done |
| ENG-01 | Constants & Explanation object | FND-02 | Must | Done |
| ENG-02 | PM2.5 & AQI to NAQI | ENG-01 | Must | Done |
| ENG-03 | Inhaled dose timeline | ENG-01 | Must | Done |
| ENG-04 | Daily air budget & passbook | ENG-03 | Must | Done |
| ENG-05 | Indoor PM2.5 model | ENG-01 | Must | Done |
| ENG-06 | Rank indoor hacks & purifier | ENG-05 | Must | Done |
| ENG-07 | Sample forecast uncertainty | ENG-01 | Must | Done |
| ENG-08 | Optimise clean windows | ENG-03, 07 | Must | Done |
| ENG-09 | Emissions, swaps & Mohalla | ENG-03, 05 | Must | Done |
| INT-01 | Google Air Quality client | FND-03 | Must | Done |
| API-01 | Request/response schemas | ENG-04 | Must | Done |
| API-02 | Passbook endpoint | API-01, INT-01 | Must | Done |
| API-03 | Plan endpoint | API-02, ENG-08 | Must | Done |
| API-04 | Indoor simulate endpoint | API-02, ENG-06 | Must | Done |
| API-05 | Swaps impact endpoint | API-02, ENG-09 | Must | Done |
| API-06 | Brief endpoint with re-plan | API-03 | Must | Done |
| API-07 | Demo profiles & story endpoints | API-02 | Must | Done |
| AGT-01 | Guardrails L1/L2 | API-01 | Must | Done |
| AGT-02 | Numeric grounding gate | AGT-01 | Must | Done |
| AGT-03 | Versioned prompt registry | — | Must | Done |
| AGT-04 | Gemini cascade & AI quota | AGT-03 | Must | Done |
| AGT-05 | ADK agent, tools & sessions | AGT-02, 04 | Must | Done |
| AGT-06 | Fallback router & composer | AGT-05 | Must | Done |
| AGT-07 | Chat endpoint | AGT-06 | Must | Done |
| AGT-08 | Evaluation harness | AGT-07 | Must | Done |
| UI-00 | Stitch screen design | — | Must | Done |
| UI-01 | Design tokens & base layout | UI-00, API-07 | Must | Done |
| UI-02 | Onboarding modal | UI-01 | Must | Done |
| UI-03 | Today passbook screen | UI-02, API-06 | Must | Done |
| UI-04 | Clean-window plan screen | UI-03 | Must | Done |
| UI-05 | Home air simulator screen | UI-03 | Must | Done |
| UI-06 | Swaps & Mohalla screen | UI-03 | Must | Done |
| UI-07 | Ask HawaKhata chat drawer | UI-03, AGT-07 | Must | Done |
| UI-08 | How it works trust page | UI-01 | Must | Done |
| UI-09 | Story mode guided tour | UI-03..08 | Must | Done |
| HRD-01 | Security audit & proof files | all above | Must | Done |
| HRD-02 | Accessibility audit | all UI | Must | Done |
| REL-01 | README with Code Map | HRD-01 | Must | Done |
| REL-02 | Deploy to Cloud Run | REL-01 | Must | Ready (manual) |
| REL-03 | Early release & score loop | REL-02 | Must | Pending deploy |
| REL-04 | Demo lock & video assets | REL-02 | Must | Local prep done |

## Parked
| Idea | Found during | Why parked |
|---|---|---|
