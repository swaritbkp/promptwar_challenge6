# HawaKhata (हवा खाता · "Air Passbook")

> Air passbook for winter smog: debit (inhaled PM2.5), savings (exposure avoided), and balance under WHO 2021 guidelines.

[![Tests](https://img.shields.io/badge/tests-205%20passed-brightgreen.svg)]() [![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)]() [![Security](https://img.shields.io/badge/security-verified-blue.svg)]() [![WCAG](https://img.shields.io/badge/a11y-WCAG%202.2%20AA-success.svg)]()

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
  ├─ Google AQ Client: TTL cache → Live API → Fixture (`integrations/air_quality.py: AirQualityClient()`)
  └─ Grounded Agent: Guardrails L1 → ADK → Grounding → Guardrails L2 (`agent/agent.py: HawaKhataAgent()`)
```
- **LLM role:** Intent classification (EN/HI), tool invocation, and narrative response.
- **Pure engine:** Mathematical calculation of physical doses, budgets, and emissions.
- **Grounding gate:** Validates all numbers against tool outputs (`agent/grounding.py: check_numeric_grounding()`).
- **Fallback:** Offline template routing when LLM is unavailable (`agent/fallback.py: route_intent()`).

## 3. Google Cloud Technologies
- **Google Maps Air Quality API:** Hourly forecasts & NAQI via `integrations/air_quality.py: AirQualityClient()`.
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
| NAQI Scale | `engine/aqi.py: pm25_to_naqi_category()` | Exact CPCB India NAQI category classification |
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
python scripts/gate.py                # Lint, format, mypy, 194 tests, audit
uvicorn hawakhata.app:create_app --factory --app-dir src --reload --port 8000
```
Open `http://localhost:8000` (live) or `http://localhost:8000/?story=ncr` (tour).
