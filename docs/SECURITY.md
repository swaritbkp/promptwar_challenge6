# Security & access design — HawaKhata

The rules every change must follow. Each feature ticket lists the rule numbers (R#) it touches.

## 1. Login
**No login, by design.** HawaKhata is a public tool for families; asking for an account would stop people at the door and require storing personal data. Family profiles live only in the user's browser (`localStorage`). Rate limits and AI quotas are the primary protection.

## 2. Who can see and do what
| Role | Can access | Can never access |
|---|---|---|
| Anyone (anonymous) | Public pages, computing endpoints with their own request data, chat | Other users' data (none stored server-side), API keys, prompts, logs |

No server records to enumerate; ID-guessing attacks have nothing to reach. Chat sessions are keyed by random UUID, bounded in number and expire (`SESSION_*` settings).

## 3. Protecting data
- HTTPS only (Cloud Run); HSTS sent when request arrives over HTTPS.
- Secrets in environment variables locally and Secret Manager in production (`config.py: Settings` uses `SecretStr`).
- Coordinates rounded to ~1 km before caching, logging or prompting; sensitivities stay in the browser.
- Server stores no personal data beyond bounded, expiring in-memory caches and chat sessions.

## 4. Inputs and APIs
- Every request validated server-side with pydantic models (`extra="forbid"`, bounded fields).
- No database, no SQL, no shell commands built from input.
- Rate limiting on every `/api/` route (`RateLimitMiddleware`), body-size limit (`BodySizeLimitMiddleware`).
- CORS not enabled (same-origin UI). Explicit allow-list required if ever added.
- No client-side price, payment or permission trust.

## 5. AI features
- **AI output is untrusted.** Inserted via `textContent` only; never `innerHTML` or evaluated as code.
- **AI keys stay on server.** Browser only speaks to `/api/v1/chat`.
- **Prompt injection defense:** User text sanitized, masked, wrapped in untrusted tags; system prompt canary blocked if outputted.
- **Usage caps per client:** Per-minute and per-day limits for Gemini-backed features (`TokenBucketLimiter`, `DailyQuota`). Deterministic path works on limit.
- **Grounded numbers:** Numbers must originate from engine or AQ API; assistant falls back rather than guess. Red-flag symptoms trigger immediate medical guidance.

## 6. Logging and monitoring
Structured JSON logs with request id, route, status, latency, data mode, model id, prompt version, grounding result and fallback flag. Never logged: user text, prompts, keys, exact coordinates.

## 7. Compliance (India)
| Requirement | Applies? | How it's handled |
|---|---|---|
| DPDP Act 2023 | Partly | No account; profile stored on user device; "Clear my data" deletes it; server keeps no personal data. |
| Health data rules | Partly | Sensitivity flags stay on device; no diagnosis or treatment advice. |
| Data residency | No | No personal data stored server-side; region `asia-south1` used. |
| Payments, children | No | No payments; no accounts. |

## 8. Absolute rules
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

## 9. Known deviations
| Rule | What's different | Why it's acceptable for now | Fix by |
|---|---|---|---|
| R2, R11 | Limits are per Cloud Run instance (in memory) and reset on restart. | `--max-instances` caps total throughput; limits are bounded and tested. | Move limiter and quota to Redis (`REDIS_URL`) if traffic grows. |

## 10. Pre-release gate
- [ ] Every rule met or listed in §9 with a fix plan.
- [ ] Dependency scan reviewed (`pip-audit` step in `scripts/gate.py`).
- [ ] Rate limit, AI quota and body limit confirmed on deployed URL.
- [ ] `docs/SECURITY_AUDIT.md` completed with proof files.
