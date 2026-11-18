# ARCHITECTURE — HawaKhata

## Layers
```
Browser (Jinja2 page + ES modules, profile in localStorage, SVG charts)
   │  JSON over HTTPS
FastAPI app (app.py: create_app)
   ├─ middleware: request-id → security headers/CSP → body-size limit → rate limit → structured logging
   ├─ api/routes.py  (thin)  →  services/*  →  engine/* (pure, no I/O)
   │                                   └──→ integrations/air_quality.py (cache → live → fixture)
   └─ /api/v1/chat → agent/guardrails.L1 → agent/agent.py (ADK, Gemini, tools=services)
                       → agent/grounding.check → agent/guardrails.L2 → response
                       ↳ on timeout / error / ungrounded twice → agent/fallback.py (deterministic)
```

## Endpoints (all JSON, versioned)
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | UI |
| GET | `/healthz` | liveness |
| GET | `/api/v1/meta` | app, agent, prompt, constants versions; data mode (live/fixture); model ids |
| POST | `/api/v1/air/forecast` | normalised hourly series for a location (PM2.5, PM10, AQI local + universal, health recs) |
| POST | `/api/v1/passbook` | F1 |
| POST | `/api/v1/plan` | F2 |
| POST | `/api/v1/indoor/simulate` | F3 |
| POST | `/api/v1/swaps/impact` | F4 |
| POST | `/api/v1/brief` | F6 |
| POST | `/api/v1/chat` | F5 |
| GET | `/api/v1/demo/profiles` | demo family list + profiles from `data/fixtures/profiles.json` |
| GET | `/api/v1/story/{story_id}` | F7 story config (profile ref, fixture, fixed clock) |
| GET | `/how-it-works` | F8 trust page |

All computing endpoints accept optional `now` (ISO-8601) and `data_source` (`auto`/`fixture`) so story
mode is deterministic without special-casing; the engine never reads the system clock.

## Error contract (every non-2xx)
```json
{"error": {"code": "UPSTREAM_TIMEOUT", "message": "human readable", "request_id": "…", "retryable": true}}
```
Codes: `VALIDATION_ERROR`, `RATE_LIMITED`, `PAYLOAD_TOO_LARGE`, `UPSTREAM_TIMEOUT`, `UPSTREAM_ERROR`,
`GUARDRAIL_BLOCKED`, `INTERNAL_ERROR`. Upstream failures degrade (fixture/fallback) before they error.

## Response envelope (2xx)
```json
{"data": {...}, "meta": {"request_id": "…", "data_mode": "live|fixture", "engine_version": "…",
 "constants_version": "v1", "prompt_version": "v1.0", "agent_version": "…", "degraded": false}}
```

## Data flow — air quality
`integrations/air_quality.get_hourly_forecast(lat, lng, hours)`:
1. Round to a ~1 km grid cell (privacy + cache hit-rate). Cache key = cell + hour bucket.
2. Cache hit → return. Miss → POST `forecast:lookup` (+ `currentConditions:lookup`) with `LOCAL_AQI`,
   `POLLUTANT_CONCENTRATION`, `HEALTH_RECOMMENDATIONS`, `DOMINANT_POLLUTANT_CONCENTRATION`; follow page tokens.
3. Timeout (config) + 1 retry with jitter; circuit breaker opens after N failures for M seconds.
4. Failure / no key → nearest fixture from `data/fixtures/` with `data_mode="fixture"`.
5. Normalise into `HourlyAirSeries` (UTC + local time, pm25, pm10, aqi_local, aqi_universal, category,
   dominant pollutant, health recs by group).

## Agent design (F5)
- ADK `LlmAgent` with instruction from `prompts/v1.0/agent_system.md`, tools:
  `get_air_forecast`, `get_family_passbook`, `plan_clean_windows`, `simulate_indoor_air`,
  `evaluate_swaps`, `get_smog_brief`, `explain_number`.
- Session memory: ADK session service (in-memory, bounded: max sessions + TTL; Redis-ready interface).
- Follow-ups: if a tool returns `missing_fields`, the agent asks ONE concise question, then continues.
- Output: `{"reply": str, "language": "en|hi", "numbers_used": [...], "tool_calls": [...], "follow_up": str|null}`.
- Grounding gate extracts every number from `reply` (Latin + Devanagari digits), allows those present in
  tool outputs (tolerance for rounding/units) plus a tiny whitelist (e.g. counts ≤ 10, years, times).
  Fail → one regeneration with the violations listed → fail again → fallback narrator.
- Model cascade: primary model id from config → secondary (flash-lite) on 429/5xx/timeout.

## Caching & limits (all bounded)
| Thing | Implementation | Bound |
|---|---|---|
| AQ responses | `TTLCache` / `RedisCache` | `CACHE_MAX_ENTRIES`, `AQ_CACHE_TTL_S` |
| Chat sessions | ADK session service wrapper | `SESSION_MAX`, `SESSION_TTL_S`, `SESSION_MAX_TURNS` |
| Rate limiter | token bucket per client hash | `RATE_LIMIT_MAX_CLIENTS` (LRU-evicted) |
| Request body | middleware | `MAX_BODY_BYTES` |

## Observability & governance
Structured JSON logs (request_id, route, latency_ms, data_mode, model, prompt_version, grounding_result,
fallback_used) — no PII. `/api/v1/meta` exposes versions. `eval/run_eval.py` writes `eval/report.json`.
