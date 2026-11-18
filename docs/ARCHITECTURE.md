# ARCHITECTURE — HawaKhata

## System Layers
```
Browser (Semantic HTML5 + ES modules, localStorage profile, SVG charts)
   │  HTTPS JSON
FastAPI app (`app.py: create_app()`)
   ├─ middleware: request-id → security headers/CSP → body-size limit → rate limit → JSON logs
   ├─ api/routes.py → services/* → engine/* (pure, zero I/O)
   │                      └──→ integrations/air_quality.py (cache → live Google API → fixture)
   └─ /api/v1/chat → agent/guardrails.L1 → agent/agent.py (ADK, Gemini cascade, tools)
                       → agent/grounding.check → agent/guardrails.L2 → response
                       └── on timeout / error / ungrounded → agent/fallback.py (deterministic)
```

## Endpoints (All JSON, Versioned)
| Method | Path | Description |
|---|---|---|
| GET | `/`, `/how-it-works` | UI pages (Jinja2) |
| GET | `/healthz`, `/api/v1/meta` | Health check & runtime metadata |
| POST | `/api/v1/air/forecast` | Normalised hourly series (PM2.5, AQI, NAQI, recs) |
| POST | `/api/v1/passbook` | Inhaled dose, daily air budget, balance, cigarette eq |
| POST | `/api/v1/plan` | Clean-window activity optimizer with uncertainty |
| POST | `/api/v1/indoor/simulate` | Single-zone indoor PM2.5 model and purifier sizing |
| POST | `/api/v1/swaps/impact` | Household & Mohalla community emission reductions |
| POST | `/api/v1/brief` | Proactive morning brief with auto re-planning |
| POST | `/api/v1/chat` | Multi-turn grounded GenAI assistant with fallback |
| GET | `/api/v1/demo/profiles`, `/api/v1/story/{id}` | Demo profiles and reproducible story tours |

## Error & Response Contract
- Non-2xx: `{"error": {"code": "CODE", "message": "text", "request_id": "...", "retryable": bool}}`
- Codes: `VALIDATION_ERROR`, `RATE_LIMITED`, `PAYLOAD_TOO_LARGE`, `UPSTREAM_TIMEOUT`, `UPSTREAM_ERROR`, `GUARDRAIL_BLOCKED`, `INTERNAL_ERROR`.
- Envelope (2xx): `{"data": {...}, "meta": {"request_id": "...", "data_mode": "live|fixture", "engine_version": "...", "constants_version": "v1", "agent_version": "...", "degraded": false}}`

## Air Quality Integration (`integrations/air_quality.py`)
1. Coordinate rounding (~1 km cell). Cache key = cell + hour.
2. TTL cache hit → return. Cache miss → POST Google Maps Air Quality `forecast:lookup`.
3. Circuit breaker opens after 3 failures; degrades seamlessly to nearest winter fixture.
4. Returns `HourlyAirSeries` with India NAQI categories and health advice.

## GenAI Pipeline (`agent/`)
1. L1 Input Guardrails: length cap, control char strip, prompt injection regex, Indian PII masking.
2. ADK Agent & Cascade: primary model (`gemini-2.5-flash`), secondary fallback (`gemini-2.5-flash-lite`).
3. Domain Tools: wrapped services (`get_air_forecast`, `get_family_passbook`, `plan_clean_windows`, etc.).
4. Grounding Gate: extracts numbers from reply, matches against tool outputs. Ungrounded output rejected.
5. L2 Output Guardrails: canary token check, medical emergency detector, prescription blocker.
6. Fallback: deterministic router (`lexicon.v1.json`) and template composer (`templates.v1.json`).
