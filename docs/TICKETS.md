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

## Completed Tickets (Phase 0, 1, 2)
- **FND-01..03**: Verified external APIs, pinned dependencies, completed constants with citations, created 96h Delhi NCR and Chandigarh air data fixtures.
- **ENG-01..09**: Pure deterministic engine (constants, NAQI, dose, budget, indoor ODE, recommendations, uncertainty, clean-window planner, emissions & swaps).
- **INT-01**: Google Air Quality API client with ~1 km coordinate rounding, circuit breaker, bounded TTL-LRU/Redis cache, and offline fixture fallback.
- **API-01..07**: Bounded Pydantic v2 schemas (`extra="forbid"`), unified 2xx `Envelope[T]`, endpoints for passbook, plan, indoor simulate, swaps impact, proactive morning brief with forecast-shift replan, and deterministic story modes.

## Remaining Tickets

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
