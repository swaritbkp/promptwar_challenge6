# Security & access design — HawaKhata

The rules every change must follow. Feature tickets list the rule numbers (R#) touched.

## 1. Login
**No login, by design.** HawaKhata is a public tool for families; personal profiles live strictly in `localStorage`. Rate limits and AI quotas provide protection.

## 2. Access Model
| Role | Can access | Can never access |
|---|---|---|
| Anyone (anonymous) | Public pages, computing endpoints with own payload, chat | Other users' data (none stored server-side), API keys, prompts, logs |

## 3. Data Protection
- HTTPS only (Cloud Run); HSTS sent over HTTPS.
- Secrets in environment variables locally and Secret Manager in production (`config.py: Settings` uses `SecretStr`).
- Coordinates rounded to ~1 km before caching, logging or prompting; health flags stay in browser.
- Server stores no personal data; in-memory caches and chat sessions expire (`SESSION_*`).

## 4. Inputs & APIs
- Every request validated server-side (`extra="forbid"`, bounded fields).
- No database, SQL, or shell execution.
- Rate limiting on every `/api/` route (`RateLimitMiddleware`), body-size limit (`BodySizeLimitMiddleware`).
- CORS not enabled (same-origin UI).

## 5. AI Guardrails
- **Untrusted output:** Inserted via `textContent` only; never `innerHTML` or evaluated.
- **Server-side keys:** Browser speaks only to `/api/v1/chat`.
- **Prompt defense:** Input sanitized, masked, tagged; canary blocked on output.
- **Usage caps:** Per-minute token bucket and per-day quota per IP. Deterministic fallback on limit.
- **Grounding:** Numbers must originate from engine or AQ API; health red flags trigger emergency notice.

## 6. Telemetry
Structured JSON logs with request id, route, latency, data mode, model id, and grounding result. Never logged: raw user text, prompts, keys, or exact coordinates.

## 7. Compliance (India)
| Requirement | Applies? | Implementation |
|---|---|---|
| DPDP Act 2023 | Partly | No server accounts; data in browser; "Clear data" deletes local state. |
| Health rules | Partly | Health flags stay on device; no medical diagnosis or drug dosing. |
| Data residency | No | No personal data stored server-side; region `asia-south1`. |
| Payments/children | No | No payments; no accounts. |

## 8. Absolute Rules
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

## 9. Known Deviations
| # | Rule | Deviation | Why acceptable | Review date |
|---|---|---|---|---|
| KD-1 | R2 | In-memory token bucket per instance | Single-container Cloud Run deployment or optional Redis cache | 2026-11-18 |
