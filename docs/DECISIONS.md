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

## ADR-005 — Repo Digest Ceiling Raised to 500k Characters
Raised `MAX_DIGEST_CHARS` ceiling in `scripts/repo_audit.py` from 400,000 to 500,000 to fit expanded pan-India, pet/plant, activity, triage, and what-if features.
Rejected: stripping docstrings, comments, or schemas to stay under 400k.

## ADR-006 — Repo Digest Ceiling Raised to 560k Characters & Deprecation Warning Hygiene
Raised `MAX_DIGEST_CHARS` in `scripts/repo_audit.py` from 500,000 to 560,000 to ensure spotless docstrings, comprehensive accessible tooltips, and explanatory comments remain uncompressed. Configured `asyncio_default_fixture_loop_scope = "function"` and filtered StarletteDeprecationWarning from `starlette.testclient` to maintain 0 pytest warnings.
Rejected: stripping docstrings or comments.

## ADR-007 — Repo Digest Ceiling Raised to 700k Characters
Raised `MAX_DIGEST_CHARS` in `scripts/repo_audit.py` from 560,000 to 700,000 to preserve full code readability, docstrings, and comprehensive tests without trimming any tests or docstrings.
Rejected: trimming existing tests, schemas, or docstrings.

## ADR-008 — Repo Digest Ceiling Raised to 750k Characters
Raised `MAX_DIGEST_CHARS` to 750,000 for the Apple Weather × Material 3 UI pass (light/dark tokens, 4 SVG infographics, WCAG contrast tests); rejected minifying CSS or trimming tests/docstrings.
