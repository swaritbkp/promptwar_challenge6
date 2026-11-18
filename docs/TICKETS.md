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
| ENG-07 | Sample forecast uncertainty (seeded) | ENG-01 | Must | Not started |
| ENG-08 | Optimise the day plan (robust clean windows) | ENG-03, ENG-07 | Must | Not started |
| ENG-09 | Compute emissions, swap deltas and community scaling | ENG-03, ENG-05 | Must | Not started |
| INT-01 | Google Air Quality client with cache, breaker, fixture fallback | FND-03 | Must | Not started |
| API-01 | Request/response schemas and envelope | ENG-04 | Must | Not started |
| API-02 | Passbook endpoint | API-01, INT-01 | Must | Not started |
| API-03 | Plan endpoint | API-02, ENG-08 | Must | Not started |
| API-04 | Indoor simulate endpoint | API-02, ENG-06 | Must | Not started |
| API-05 | Swaps impact endpoint | API-02, ENG-09 | Must | Not started |
| API-06 | Brief endpoint with forecast-shift re-plan | API-03 | Must | Not started |
| API-07 | Demo profiles and story endpoints | API-02 | Must | Not started |
| AGT-01 | Input/output guardrails | API-01 | Must | Not started |
| AGT-02 | Numeric grounding gate | AGT-01 | Must | Not started |
| AGT-03 | Versioned prompt registry | — | Must | Not started |
| AGT-04 | Gemini client: cascade, timeouts, AI quota | AGT-03 | Must | Not started |
| AGT-05 | ADK agent with tools, sessions and follow-ups | AGT-02, AGT-04, API-06 | Must | Not started |
| AGT-06 | Deterministic fallback router and composer | AGT-05 | Must | Not started |
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

## Tickets

**FND-01 — Verify external APIs and pin dependencies.** Story: as the builder, I want verified API
facts so code isn't built on guesses. AC: ADR entries record docs URL + date for Air Quality API
(current conditions, forecast, extra computations, India local index, pagination), google-genai (model
ids, structured output, function calling, thinking config, sampling-param deprecation) and google-adk
(agent, tools, runner, sessions); `requirements.txt` pins direct deps exactly; gate GREEN. R1.

**FND-02 — Verify and complete constants.** AC: every `verified:false` checked against its source or
replaced by a better primary source; every `null` filled with value + range + citation, or explicitly
left `verified:false` with a conservative range and a note; no invented citations. —

**FND-03 — Fixtures.** AC: two files, 96 hourly points each, exact API response shape, realistic winter
diurnal pattern, `synthetic` flag honest, each < 40 KB; a contract test parses both. —

**ENG-01 — Constants + Explanation.** AC: `load_constants()` validates schema and fails loudly on bad
data; `get_constant(id)` returns value/unit/range/source; `Explanation` (formula, inputs, constants_used,
sources, assumptions) is frozen and JSON-serialisable. —

**ENG-02 — NAQI categories.** AC: `pm25_to_naqi_category()` and `aqi_to_category()` cover every
boundary value (table test incl. 30/31, 250/251); each category has a text label key and icon key. —

**ENG-03 — Member dose.** AC: `inhalation_rate_m3_per_h(age_band, activity)`; `build_member_timeline()`
from schedule blocks with defaults; `compute_member_dose()` returns hourly dose, total, top-3
contributors, Explanation; properties: dose ≥ 0 and linear in concentration. —

**ENG-04 — Budget & passbook.** AC: `daily_air_budget_ug()` = WHO 24h × daily IR;
`build_passbook_entry()` returns debit, budget, balance, overspend ratio, cigarette equivalent (labelled
rough) and Explanation; property: overspend = debit/budget. —

**ENG-05 — Indoor model.** AC: exact exponential step equals analytic solution (1e-9); properties: more
CADR never raises C, adding a source never lowers C, C ≥ 0; sub-hour events averaged. —

**ENG-06 — Indoor recommendations.** AC: `recommend_ventilation_hours()` returns only hours where
outdoor < indoor (empty list + reason otherwise); `recommend_purifier_cadr()` with sufficiency verdict;
`rank_indoor_hacks()` top 5 by Δ dose with explanations. —

**ENG-07 — Uncertainty.** AC: seeded `sample_forecast_paths()` deterministic for same seed; `p50_p90()`;
sample count from config. —

**ENG-08 — Planner.** AC: never moves fixed blocks, never overlaps a member's activities, respects
windows; objective expected + λ·P90; result dose ≤ usual dose; "already optimal" flag; Big-O in docstring. —

**ENG-09 — Emissions & swaps.** AC: `activity_emissions()` with low/central/high; `evaluate_swap()`
Δbreathe per member + Δemit per day/week/month; `scale_to_community()` linear, zero at participation 0. —

**INT-01 — AQ client.** AC: coordinates rounded ~1 km before cache keys/logs; bounded cache; timeout +
1 jittered retry; breaker opens after 3 failures for 60 s (clock injected); no key/failure → nearest
fixture with `data_mode=fixture`; pagination merged; key never logged. R1, R8.

**API-01 — Schemas.** AC: pydantic v2 models with `extra="forbid"`, bounded strings/numbers/lists;
envelope with meta (versions, data_mode, degraded). R6.

**API-02..API-06 — Computing endpoints.** AC for each: happy path, validation error in the error
contract, degraded path when upstream is down, accepts optional `now` + `data_source`, handler ≤ 15
lines delegating to a service. API-06 adds `detect_forecast_shift()` + `replan_if_needed()` with the
threshold from config. R6.

**API-07 — Demo & story.** AC: `/api/v1/demo/profiles` returns fixture profiles; `/api/v1/story/{id}`
returns config from `data/story.v1.json`; unknown id → 404 contract; identical outputs on repeat calls. —

**AGT-01 — Guardrails.** AC: sanitize, injection detection (EN+HI patterns from data), PII masking
before any LLM call or log, red-flag detection, output policy (canary, no diagnosis/dosing). Tests for
each pattern. R10, R12.

**AGT-02 — Grounding gate.** AC: extracts Latin/Devanagari numbers, %, ×, ranges, Indian grouping;
allowed set from tool outputs with rounding variants; whitelist; returns violations; ≥ 95 % coverage. R10.

**AGT-03 — Prompt registry.** AC: loads `prompts/<version>/*.md` with front matter; placeholder fill;
bounded cache; version exposed in meta. —

**AGT-04 — Gemini client.** AC: model ids + timeout from config; no sampling params; cascade primary →
fallback on 429/5xx/timeout; `DailyQuota` + per-minute limit per client for every AI feature; quota hit
→ friendly message, deterministic path still works. R11.

**AGT-05 — Agent.** AC: ADK agent with tools over services (profile bound server-side, not passed by
the LLM); bounded sessions (max, TTL, turns); one follow-up question when a tool reports
`missing_fields`; reply in user language; structured output envelope. R10, R11.

**AGT-06 — Fallback.** AC: intent routing from `data/lexicon.v1.json` (no names in code); replies
composed from tool output + per-intent per-language templates in `data/templates.v1.json`. —

**AGT-07 — Chat endpoint.** AC: L1 → agent → grounding (≤ 1 regeneration) → L2 → envelope; timeout →
fallback; quota → 429 contract with message; never returns raw HTML. R10, R11, R12.

**AGT-08 — Eval.** AC: `eval/run_eval.py --mode fake|live` over ≥ 20 golden cases; grounding and
guardrail pass-rate 100 % in fake mode; p50/p95 latency; non-zero exit on failure. —

**UI-00 — Stitch designs.** AC: screens per `docs/UX_SPEC.md` generated from `DESIGN.md`; chosen
variants + notes recorded; exports kept out of the repo. —

**UI-01 — Foundation.** AC: tokens from DESIGN.md (light/dark/high-contrast), icon sprite, base template
with landmarks + skip link, router with focus management, i18n EN/HI, fixture banner. R8.

**UI-02..UI-06 — Screens.** AC for each: matches the Stitch design and UX_SPEC; loading, empty, error,
populated states; every number has "Why this number?"; keyboard-complete; Hindi renders correctly;
static a11y tests pass.

**UI-07 — Ask sheet.** AC: states *AI thinking* (send disabled, progress text), *AI unavailable* (says
what still works), *AI doesn't know* (honest message + where to look); replies inserted with
`textContent` only; number chips link to explanations; red-flag card first; sensitive-data hint under
the input. R10.

**UI-08 — How it works.** AC: architecture SVG, Google services, constants table rendered from data,
privacy statement; accessible. —

**UI-09 — Story mode.** AC: 8 steps from `data/story.v1.json`; keyboard → ← Enter Esc; captions via
`aria-live`; numbers identical across 3 runs; works without keys. —

**HRD-01 — Security audit.** AC: `docs/SECURITY_AUDIT.md` created from the private template; every item Pass/Fail/N/A/Unverified with a
proof file; every finding passed through the verification gate; real findings fixed with tests;
theoretical ones logged as Known Deviations. Ideally run with a different model than the builder. R1–R12.

**HRD-02 — Accessibility audit.** AC: keyboard walk-through of every screen, contrast checked,
Lighthouse a11y 100 on four main screens, 200 % zoom and 360 px width OK. —

**REL-01 — README.** AC: follows the template; Code Map citations verified by the repo audit. —

**REL-02 — Deploy.** AC: Cloud Run with Secret Manager; `/healthz`, `/api/v1/meta` (live), `/`,
`/?story=ncr` verified on the URL. R1.

**REL-03 — Early release + score-driven improvement rounds.** AC: first release as soon as REL-02
passes; every round's scores logged with the commit hash; each round changes at most two quality areas,
each change backed by a file:line cause and a test; changes re-verified before the next release. —

**REL-04 — Demo & video assets.** AC: story numbers recorded into the demo script; recordings captured;
submission text drafted. —

## Parked (ideas found while building — not in scope until P0 is Done)
| Idea | Found during | Why parked |
|---|---|---|
