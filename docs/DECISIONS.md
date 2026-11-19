# Decisions

Every structural decision with reason and alternative rejected.

| # | Decision | Choice | Why (and what was rejected) | Status |
|---|---|---|---|---|
| D1 | Numbers source | Deterministic engine + Google AQ API; LLM narrates; grounding gate | Verifiable numbers. Rejected: model estimating exposure (hallucination risk). | Accepted |
| D2 | App structure | Modular FastAPI (routes → services → engine) | Simple, scales on Cloud Run. Rejected: microservices. | Accepted |
| D3 | Frontend | Jinja2 + vanilla ES modules + CSS tokens from Stitch | Strict CSP, no build tooling. Rejected: React/Tailwind CDN. | Accepted |
| D4 | Login | None; profile in browser storage | Zero friction, no personal data liability. Rejected: user accounts. | Accepted |
| D5 | Caching | Bounded TTL-LRU default; Redis optional | Fixed memory bound. Rejected: unbounded dict. | Accepted |
| D6 | Abuse limits | Per-minute token bucket + per-day AI quota per IP | Protects no-login endpoints. Rejected: unthrottled access. | Accepted |
| D7 | Primary metric | PM2.5 µg/m³ for dose & budget; NAQI for display | PM2.5 drives health risk. Rejected: AQI index as dose. | Accepted |
| D8 | Air budget | WHO 2021 24h guideline × breathing volume | Personalized and age-aware. Rejected: uniform budget. | Accepted |
| D9 | Determinism | Explicit `now` + `data_source` on endpoints | Reliable demos. Rejected: hardcoded numbers in code. | Accepted |
| D10 | External APIs | Verified Google AQ API (`ind_cpcb`), google-genai 2.34, adk 2.14 | Verified shapes (ADR-004). Rejected: unverified assumptions. | Accepted |

## ADR-004 — Verified External API Specifications & SDK Contracts
Verified: 2026-11-18.
- **Air Quality API**: `POST airquality.googleapis.com/v1/forecast:lookup` (96h). Auth `X-Goog-Api-Key`. Local code `ind_cpcb`. Dominant pollutant `pm25`. Coordinates rounded to ~1 km.
- **Google GenAI (`google-genai==2.34.0`)**: Models: `gemini-2.5-flash` (primary), `gemini-2.5-flash-lite` (fallback).
- **Google ADK (`google-adk==2.14.1`)**: `LlmAgent`, `Runner`, `InMemorySessionService` bounded by `SESSION_*`.
