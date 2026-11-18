# Decisions

Every structural decision with its reason and the alternative rejected. A decision is never silently
reversed: write a new entry that supersedes the old one and says why.

| # | Decision | Choice | Why (and what was rejected) | Status |
|---|---|---|---|---|
| D1 | Who produces numbers | Deterministic engine + Google AQ API; LLM narrates; grounding gate | Families must be able to verify every figure. Rejected: letting the model estimate exposure (unverifiable, can hallucinate). | Accepted |
| D2 | App structure | One FastAPI app with layered modules (routes → services → engine) | Simplest thing that scales on Cloud Run. Rejected: microservices (no problem they would solve). | Accepted |
| D3 | Frontend | Jinja2 + vanilla ES modules + CSS tokens; screens designed in Stitch and translated | Strict CSP, tiny payload, no build step. Rejected: React/Tailwind export (CDN/build tooling, larger bundle). | Accepted |
| D4 | Login | None; profile in browser storage | No personal data on the server; zero-friction start. Rejected: accounts (friction + data liability). | Accepted |
| D5 | Caching | `CacheBackend` protocol: bounded TTL-LRU default, Redis when `REDIS_URL` is set | Bounded memory; shared cache when scaled. Rejected: unbounded dict (memory risk). | Accepted |
| D6 | Abuse limits | Per-minute token bucket + per-day AI quota, bounded client tables | No-login app relies on limits. Rejected: no limits (cost and abuse risk). | Accepted |
| D7 | Primary metric | PM2.5 µg/m³ for dose and budget; NAQI for display | PM2.5 drives health risk and infiltrates indoors. Rejected: AQI number for dose (not a concentration). | Accepted |
| D8 | Air budget | WHO 2021 24-h guideline × member breathing volume | Personal, explainable, age-aware. Rejected: one budget for everyone (ignores children's higher intake per kg). | Accepted |
| D9 | Demo determinism | Optional `now` + `data_source` on every computing endpoint; story config in data | Reproducible demos without special-case code. Rejected: hardcoded demo numbers. | Accepted |
| D10 | External API facts | Verified Google AQ API contract (ind_cpcb), google-genai 2.34.0, and google-adk 2.14.1 | Never build on guessed API shapes. Detailed in ADR-004 below. | Accepted |

## ADR-004 — Verified External API Specifications & SDK Contracts

Verified on: 2026-11-18.

### 1. Google Maps Platform Air Quality API
- **Official Docs URL**: `https://developers.google.com/maps/documentation/air-quality`
- **Endpoints**:
  - `POST https://airquality.googleapis.com/v1/currentConditions:lookup`
  - `POST https://airquality.googleapis.com/v1/forecast:lookup` (hourly forecast up to 96 h, paginated with `pageSize` and `pageToken` / `nextPageToken`)
- **Authentication**: Prefer `X-Goog-Api-Key` header over query parameter to prevent key leakage in query logs.
- **Request Body Configuration**:
  ```json
  {
    "location": {"latitude": 28.46, "longitude": 77.03},
    "period": {"startTime": "<UTC RFC3339>", "endTime": "<UTC RFC3339>"},
    "universalAqi": true,
    "languageCode": "en",
    "extraComputations": [
      "LOCAL_AQI",
      "HEALTH_RECOMMENDATIONS",
      "POLLUTANT_CONCENTRATION",
      "DOMINANT_POLLUTANT_CONCENTRATION",
      "POLLUTANT_ADDITIONAL_INFO"
    ],
    "pageSize": 96
  }
  ```
- **India Local AQI Code Resolution**:
  - The local index code for India (Central Pollution Control Board / National AQI) is lowercase **`ind_cpcb`**.
  - Universal AQI code is **`uaqi`**.
  - Category bands for `ind_cpcb`: `Good`, `Satisfactory`, `Moderate`, `Poor`, `Very Poor`, `Severe`.
  - Dominant pollutant for winter smog: `pm25`.
- **Privacy & Caching**: Lat/lng coordinates are rounded to 2 decimal places (~1 km grid cell) before generating cache keys or sending to external logs/APIs.

### 2. Google GenAI SDK (`google-genai==2.34.0`)
- **Official Docs URL**: `https://ai.google.dev`
- **Client**: `from google import genai; client = genai.Client(api_key=...)`
- **Verified Models**:
  - Primary: `gemini-2.5-flash` (balanced latency, high throughput, native thinking / structured outputs).
  - Fallback: `gemini-2.5-flash-lite` (low latency, fast token turnarounds for simple narration).
- **Structured Output**: Passed via `types.GenerateContentConfig(response_mime_type="application/json", response_schema=Schema)`.
- **Function Calling / Tools**: Passed via `types.GenerateContentConfig(tools=[...])`.
- **No-Sampling-Params Rule**: `temperature`, `top_p`, and `top_k` are deprecated for Gemini 2.0/2.5 models and must NOT be set in API calls. Behaviour is controlled via system prompts, schemas, and thinking parameters.

### 3. Google ADK Agent Framework (`google-adk==2.14.1`)
- **Official Docs URL**: `https://google.github.io/adk-docs/`
- **Components**:
  - Agent: `google.adk.agents.llm_agent.LlmAgent`
  - Runner: `google.adk.runners.Runner`
  - Session Store: `google.adk.sessions.InMemorySessionService` wrapped by bounded memory management (`SESSION_MAX`, `SESSION_TTL_S`, `SESSION_MAX_TURNS`).
- **Tool Adapter Contract**: Services are wrapped in thin Python callables with typed parameters and descriptive docstrings; return payloads include computed values, formula citations, and explicit `missing_fields` arrays for follow-up questions.

