# HawaKhata (हवा खाता · "Air Passbook")

> Air passbook for winter smog: debit (inhaled PM2.5), savings (exposure avoided), and balance under WHO 2021 guidelines.

[![Tests](https://img.shields.io/badge/tests-248%20passed-brightgreen.svg)]() [![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)]() [![Security](https://img.shields.io/badge/security-verified-blue.svg)]() [![WCAG](https://img.shields.io/badge/a11y-WCAG%202.2%20AA-success.svg)]()

## 1. Problem → Solution
| Brief Clause | Feature | Engine Citation |
|---|---|---|
| "navigate winter smog" | Family Passbook (Debit, Budget, Balance, Cigs) | `engine/dose.py: compute_member_dose()`, `engine/budget.py: daily_air_budget_ug()` |
| "low-emission routines" | Clean-Window Planner (robust P90) | `engine/planner.py: optimise_day_plan()` |
| "indoor air hacks" | Mass-Balance Simulator & Purifier Sizing | `engine/indoor_model.py: simulate_indoor_pm25()` |
| "sustainable alternatives" | Clean Swaps & Mohalla Multiplier | `engine/swaps.py: evaluate_swap()`, `engine/swaps.py: scale_to_community()` |
| "GenAI-powered assistant" | Grounded bilingual agent (EN/HI) with fallback | `agent/agent.py: HawaKhataAgent()`, `agent/grounding.py: check_numeric_grounding()` |
| "explaining impact" | Daily Smog Brief & Metric Provenance | `services/brief_service.py: generate_morning_brief()`, `services/passbook_service.py: compute_family_passbook()` |

## 2. Core Architecture: "Gemini Proposes, Code Decides"
```
Browser (Semantic HTML + ES Modules, LocalStorage)
  │ HTTPS JSON Envelope
FastAPI Gateway (`app.py: create_app()`)
  ├─ Middleware: RequestContext → SecurityHeaders → BodyLimit → RateLimit (`core/middleware.py: SecurityHeadersMiddleware()`)
  ├─ Services Layer: Passbook, Planner, Indoor, Swaps, Brief (`services/brief_service.py: generate_morning_brief()`)
  ├─ Pure Engine: Dose, mass-balance, NAQI, swaps (`engine/dose.py: compute_member_dose()`)
  ├─ AQ Client: TTL cache → Open-Meteo live (keyless, primary) → Google AQ (secondary) → Fixture (`integrations/air_quality.py: AirQualityClient()`)
  ├─ Geocoding proxy: any Indian city/town, server-side only (`integrations/geocoding.py: GeocodingClient()`)
  └─ Grounded Agent: Guardrails L1 → ADK → Grounding → Guardrails L2 (`agent/agent.py: HawaKhataAgent()`)
```
- **LLM role:** Intent classification (EN/HI), tool invocation, and narrative response.
- **Pure engine:** Mathematical calculation of physical doses, budgets, and emissions.
- **Grounding gate:** Validates all numbers against tool outputs (`agent/grounding.py: check_numeric_grounding()`).
- **Fallback:** Offline template routing when LLM is unavailable (`agent/fallback.py: route_intent()`).

## 3. Google Cloud Technologies
- **Open-Meteo Air Quality (primary, keyless):** Real hourly PM2.5 + PM10 for every Indian coordinate, passed through unmodified (`integrations/air_quality.py: parse_open_meteo_hourly()`).
- **Google Maps Air Quality API (secondary):** Used only if Open-Meteo fails and a key is set, via `integrations/air_quality.py: AirQualityClient()`.
- **Google GenAI (`google-genai==2.34.0`):** Cascade (`gemini-2.5-flash` → `gemini-2.5-flash-lite`) via `integrations/gemini.py: GeminiCascadeClient()`.
- **Google ADK (`google-adk==2.14.1`):** Domain tool wrapping & sessions in `agent/agent.py: HawaKhataAgent()`.
- **Cloud Run & Logging:** Non-root container with JSON logs via `core/logging.py: configure_logging()`.

## 4. Code Map
| Quality Area | Architectural File & Method | Evidence |
|---|---|---|
| Scaffold | `app.py: create_app()` | FastAPI factory mounting routers and middleware |
| Config | `config.py: Settings()` | Immutable BaseSettings for all environment variables |
| Errors | `core/errors.py: AppError()` | Standardized machine/human JSON error envelope |
| Cache | `core/cache.py: TTLCache()` | Bounded LRU cache with TTL eviction |
| Rate Limits | `core/rate_limit.py: TokenBucketLimiter()` | IP-keyed token bucket rate limiting with Retry-After |
| Security | `core/middleware.py: SecurityHeadersMiddleware()` | Strict CSP without unsafe-inline or external CDNs |
| Inhaled Dose | `engine/dose.py: compute_member_dose()` | EPA rates combined with micro-environment factors |
| Air Budget | `engine/budget.py: daily_air_budget_ug()` | WHO 2021 24h limit (15 µg/m³) × breathing volume |
| NAQI Scale | `engine/aqi.py: pm25_to_naqi_category()` | CPCB NAQI bands read from `data/constants.v1.json` |
| GRAP Stages | `engine/aqi.py: aqi_to_grap_stage()` | NAQI → GRAP Normal / I–IV with EN+HI advisories |
| Mask Filtration | `engine/dose.py: compute_masked_activity_dose()` | None 1.0 / Surgical 0.65 / N95 0.15 × trip dose vs WHO budget |
| 3-Slot Brief | `engine/planner.py: summarize_day_parts()` | Morning 06–11h · Afternoon 12–16h · Evening 17–21h |
| Clock Alignment | `engine/planner.py: align_to_clock()` | Forecasts start "now"; windows use true clock hours |
| Indoor Model | `engine/indoor_model.py: simulate_indoor_pm25()` | Single-zone ODE solved via exact exponential steps |
| Planner | `engine/planner.py: optimise_day_plan()` | Combinatorial search avoiding outdoor peaks |
| Swaps | `engine/swaps.py: scale_to_community()` | Linear neighborhood scaling of avoided emissions |
| Smog Brief | `services/brief_service.py: generate_morning_brief()` | Cleanest windows, alerts, and auto-replans |
| Guardrails | `agent/guardrails.py: detect_prompt_injection()` | Injection detection, PII masking, medical triage |
| Grounding | `agent/grounding.py: check_numeric_grounding()` | Verifies numbers against tool execution output |
| Fallback | `agent/fallback.py: route_intent()` | Lexicon router & template composer without LLM |

## 5. Security & Accessibility
- **Zero Server PII:** Profiles stay in `localStorage`; coordinates rounded to ~1 km (`integrations/air_quality.py: AirQualityClient()`).
- **Strict CSP:** Headers enforce `default-src 'self'` and block inline scripts. Canary token defends prompts.
- **WCAG 2.2 AA:** Landmarks (`<main>`, `<nav>`), skip links, high contrast, reduced-motion support.

## 6. Testing & Quickstart
```bash
python scripts/gate.py                # Lint, format, mypy, tests + coverage, audit, pip-audit, eval
uvicorn hawakhata.app:create_app --factory --app-dir src --reload --port 8000
```
Open `http://localhost:8000` (live) or `http://localhost:8000/?story=ncr` (tour).

## 7. Evaluator Quick-Start & Sample Inputs
**Run it (no keys needed — Open-Meteo is keyless):**
```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
uvicorn hawakhata.app:create_app --factory --app-dir src --port 8000
docker build -t hawakhata . && docker run -p 8080:8080 hawakhata       # container (non-root, $PORT)
```
**Live data, visibly sourced.** The Today brief shows a pill such as `Source: Open-Meteo Live AQ · PM2.5 184 / PM10 262 µg/m³ · Updated 18:30 IST`. Chain: Open-Meteo → Google AQ (only with `GOOGLE_MAPS_API_KEY`) → offline fixture (always in `APP_ENV=test`). Every number is computed in `engine/` — Gemini only narrates (`agent/grounding.py: check_numeric_grounding()`).

**1-click Quick Scenarios (Today tab)** — each swaps city + household + plan defaults (`services/story_service.py: load_personas()`):
| Scenario | What to look at |
|---|---|
| Delhi NCR Family (Child + Senior + Adult) | GRAP pill (tap for advisories), member bars, Morning/Afternoon/Evening strip |
| Mumbai Daily Commuter | Auto/bike commute plan, lower coastal AQI, "GRAP: Not in force" |
| Kolkata Student Athlete | Teen `run` plan → Plan tab mask toggle (None → N95 cuts the trip dose ~85%) |
| Chandigarh Senior + Pets | Pet Advisor (dog walk minutes, indoor bird warnings) |

**Sample chat prompts (Ask drawer has these as 1-click chips, EN + HI):**
1. `Is it safe for Dadi to walk at 7 AM or 4 PM today?` → direct 07:00 vs 16:00 PM2.5/AQI/dose comparison, no follow-up question.
2. `Which day in the next 4 days is best for market shopping?` → 4-day slots from `engine/planner.py: optimize_multi_day_activity()`.
3. `Is a short dog walk safe today, and are my indoor birds okay?` → species guidance.
4. `How do I cut smoke from tadka cooking, and what purifier size do I need?` → indoor hacks + CADR sizing.
5. Guardrail check: `What inhaler dose should my child take today?` → medical refusal (`agent/guardrails.py: detect_medical_dosing_request()`).

**More to try:** Location → search any Indian town (e.g. Kochi, Patna) via `GET /api/v1/locations/search?q=` (server-side proxy); 🔊 Listen reads a 15–20 s brief in `en-IN` / `hi-IN` (browser Web Speech API, no network); toggle हिन्दी in the header.
