# ARCHITECTURE — HawaKhata

## System Layers
```
Browser (Semantic HTML5 + ES modules, localStorage profile, SVG charts)
   │  HTTPS JSON
FastAPI app (`app.py: create_app()`)
   ├─ middleware: request-id → security headers/CSP/Cache-Control → body limit → rate limit → GZip (innermost, ≥500 B) → JSON logs
   ├─ api/routes.py → services/* → engine/* (pure, zero I/O)
   │                      └──→ integrations/air_quality.py (cache → Open-Meteo live (primary, keyless) → Google AQ (fallback) → fixture)
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

## Response Contract
- Non-2xx: `{"error": {"code": "CODE", "message": "text", "request_id": "...", "retryable": bool}}`
- Envelope: `{"data": {...}, "meta": {"request_id": "...", "data_mode": "live|fixture", ...}}`

## Air Quality & GenAI Pipeline
1. Round coords (~1 km). Bounded TTL cache → Open-Meteo live → Google AQ (key only) → fixture, behind circuit breakers.
2. L1 Guardrails (sanitize, injection, Indian PII masking) → ADK agent & Gemini cascade.
3. Domain tools call services; numeric grounding gate checks reply numbers against tool output.
4. L2 Guardrails (canary, medical emergency triage); deterministic fallback on timeout or error.
