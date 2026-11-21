# Decisions (ADRs)

Format: **Context → Decision → Consequences** (with the rejected alternative). Status of all: Accepted.

## ADR-001 — Numbers come from code, never the LLM
- **Context:** Health numbers that are hallucinated are harmful.
- **Decision:** Pure `engine/` plus AQ providers produce every figure; Gemini only understands, plans and narrates; `agent/grounding.py` rejects ungrounded numbers.
- **Consequences:** Verifiable output and a deterministic fallback; plainer prose when the gate fires. Rejected: model-estimated exposure.

## ADR-002 — Modular FastAPI, no login, no database
- **Context:** Single-container Cloud Run app serving anonymous families.
- **Decision:** routes → services → engine; profiles stay in browser `localStorage`; bounded TTL-LRU cache (Redis optional); per-IP minute token bucket and daily AI quota.
- **Consequences:** Zero PII liability and fixed memory; no cross-device sync; limiter is per instance (KD-1). Rejected: microservices, user accounts, unbounded dicts.

## ADR-003 — Frontend: Jinja2 + vanilla ES modules + CSS tokens
- **Context:** Strict CSP and no build tooling.
- **Decision:** Semantic HTML, ES modules, token-driven Light/Dark CSS, SVG infographics built with `createElementNS`.
- **Consequences:** No inline scripts or CDNs; contrast is unit-tested (52 pairs, min 5.31:1). Rejected: React, Tailwind CDN.

## ADR-004 — Verified external API contracts
- **Context:** SDK and API shapes must not be assumed. Verified 2026-11-18.
- **Decision:** Google AQ `POST /v1/forecast:lookup` (`ind_cpcb`, coordinates rounded ~1 km); `google-genai==2.34.0` with `gemini-3.5-flash` → `gemini-3.5-flash-lite`; `google-adk==2.14.1` (`LlmAgent`, `Runner`, bounded `InMemorySessionService`).
- **Consequences:** Pinned, tested clients. Rejected: unverified assumptions.

## ADR-005 — Dose model: PM2.5 × breathing volume vs WHO 2021
- **Context:** Personalised, age-aware budgets are needed.
- **Decision:** PM2.5 µg/m³ drives dose and budget (WHO 24-h guideline 15 × EPA breathing volume); NAQI is display only; masks use Cherrie 2018 leakage factors.
- **Consequences:** Explainable per-member numbers. Rejected: AQI index as dose, uniform budget.

## ADR-006 — Open-Meteo is the primary, keyless air-data source
- **Context:** Judges and families must get live data with zero keys.
- **Decision:** Chain Open-Meteo Live AQ (PM2.5 + PM10) → Google AQ (only with key) → fixture, each behind a circuit breaker, cached 30 min per ~1 km geo-cell; data passed through unmodified and labelled with source and time.
- **Consequences:** Never crashes offline; regional grid can differ from CPCB monitors. Rejected: Google AQ as sole source.

## ADR-007 — Determinism for demos
- **Context:** Demo and tests must be reproducible.
- **Decision:** Explicit `now` and `data_source`; story mode uses a fixed clock and fixtures; `APP_ENV=test` forces fixtures.
- **Consequences:** Identical numbers every run. Rejected: hardcoded numbers in code.

## ADR-008 — Repo digest ceiling (400k → 900k chars)
- **Context:** `scripts/repo_audit.py` caps the reviewable digest; features grew (pan-India, pets, 4 SVG infographics, WCAG tests).
- **Decision:** Raised stepwise to 500k, 560k, 700k, 750k, 760k (Sprint 1, ADR-010) and now 900k (`MAX_DIGEST_CHARS`): an explicit, owner-approved cap for the `feat/faang-hardening` track (Sprints 2–3: Redis state, SSE, chaos tests, `loadtests/`), which stay counted in the digest rather than excluded. Do not raise again; tighten docs instead.
- **Consequences:** Docstrings, tests and CSS stay unminified. Rejected: stripping docstrings, comments, tests or minifying CSS.

## ADR-009 — Desktop top-nav, innermost GZip, `/api/v1/meta` telemetry
- **Context:** The left rail wasted desktop width; outer `BaseHTTPMiddleware` layers re-stream bodies so compression never saw a full body; operators needed health insight.
- **Decision:** Desktop uses a top navigation bar (mobile keeps the bottom bar); `GZipMiddleware(minimum_size=500)` is registered first (innermost); `/api/v1/meta` adds a read-only `runtime` block (`cache_backend`, `provider_chain`, `circuit_breakers`, `grounding_gate`, `rate_limit_enabled`).
- **Consequences:** Smaller payloads and a visible degradation state; telemetry never exposes keys or URLs. Rejected: gzip at the outer layer, a separate admin endpoint.

## ADR-010 — Spoof-proof client IP, liveness vs readiness, stdlib metrics
- **Decision:** Client IP = the `TRUSTED_PROXY_HOPS`-th `X-Forwarded-For` entry from the right (Cloud Run GFE = 1), `ipaddress`-validated, else the peer. `/healthz` (Docker `HEALTHCHECK`) has no dependencies; `/readyz` checks config, prompts and a 1 s Redis ping, never upstream APIs. Logs carry `X-Cloud-Trace-Context`; `/metrics` is a stdlib Prometheus exporter with bounded labels.
- **Rejected:** leftmost XFF (spoofable), `prometheus-client` (a dependency for six series), upstream calls in `/readyz` (blips would restart healthy containers).

## ADR-011 — Redis-shared state with in-memory failover; stage-only SSE
- **Decision:** With `REDIS_URL` set, one shared client backs the AQ cache, chat sessions (JSON turn list, `SETEX` sliding TTL, bounded turns) and rate-limit buckets (one atomic Lua script, Redis `TIME` as the single clock). Any transient Redis error degrades that call to in-memory and counts `hawakhata_upstream_errors_total{provider="redis"}`; `/readyz` reports 503 so traffic drains, but no request fails. `POST /api/v1/chat/stream` streams only fixed stage labels (`aq`, `gemini`, `grounding`) and then the same verified envelope as `POST /api/v1/chat`; `/metrics` takes an optional constant-time bearer token.
- **Rejected:** token-by-token LLM streaming (would show numbers before the grounding gate), failing closed on a Redis outage (a cache blip would become user-facing 429/500s), WATCH/MULTI retries for sessions (two-key race is harmless; one write per turn).
