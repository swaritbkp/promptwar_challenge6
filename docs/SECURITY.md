# Security & access design — HawaKhata

The rules every change must follow. Feature tickets list the rule numbers (R#) touched.

## 1. Login & Access Model
No login, by design. Personal profiles live strictly in `localStorage`. Public endpoints computing over own payload; server stores no user accounts or profiles.

## 2. Data Protection & Inputs
- HTTPS only; HSTS enabled. Secrets in environment variables (`config.py: Settings` with `SecretStr`).
- Coordinates rounded to ~1 km before caching/logging/prompting. Health flags stay in browser.
- In-memory caches (`TTLCache`) and sessions (`SessionStore`) bounded by size and TTL.
- Server-side request validation (`extra="forbid"`). Rate limiting and body size limits on all routes. No CORS wildcard.

## 3. AI Guardrails
- AI output inserted via `textContent` only; never evaluated or inserted as HTML.
- Browser speaks only to `/api/v1/chat`; keys never leave backend.
- Prompt injection detector, Indian PII masking, canary token check, and medical emergency detector.
- Token bucket per-minute limiter and daily quota per hashed client IP.
- Grounding gate rejects ungrounded numbers; deterministic fallback on limit or error.

## 4. Telemetry & Compliance
- JSON logs with request ID, route, latency, data mode, model, and grounding result. Never logs PII, prompts, keys, or exact coordinates.
- DPDP Act compliant: "Clear data" deletes local state; no server accounts; region `asia-south1`.

## 5. Absolute Rules
| # | Rule |
|---|---|
| R1 | No secret, API key or password in source control, any commit, any branch. |
| R2 | Every `/api/` endpoint is rate-limited (no-login app). |
| R3 | No server-side storage of personal data; caches and sessions are bounded and expire. |
| R4 | Coordinates rounded before cache keys, logs and prompts. |
| R5 | Security headers + strict CSP on every response; no inline scripts, no third-party CDNs. |
| R6 | Every input validated on the server before use. |
| R7 | Dependencies pinned and scanned for known vulnerabilities before release. |
| R8 | No sensitive data in browser code, URLs or logs. |
| R9 | Every security fix gets a regression test. |
| R10 | AI output is never inserted as HTML, executed, or trusted for numbers without the grounding gate. |
| R11 | AI keys never reach the browser; every AI feature has per-client minute and day limits. |
| R12 | User text is masked for PII and checked for prompt injection before any model call or log. |

## 6. Known Deviations
| # | Rule | Deviation | Why acceptable | Review date |
|---|---|---|---|---|
| KD-1 | R2 | In-memory token bucket per instance | Single-container Cloud Run deployment or optional Redis cache | 2026-11-18 |
