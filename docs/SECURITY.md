# Security & access design — HawaKhata

The rules every change must follow. Each feature ticket lists the rule numbers (R#) it touches.

## 1. Login
**No login, by design.** HawaKhata is a public tool for families; asking for an account would stop
people at the door and would mean storing personal data we don't need. The family profile lives only in
the user's browser (`localStorage`). Because there is no login, **rate limits and AI quotas are the main
protection** (§4, §5).

## 2. Who can see and do what
| Role | Can access | Can never access |
|---|---|---|
| Anyone (anonymous) | Public pages, computing endpoints with their own request data, chat | Other users' data (none is stored server-side), API keys, prompts, logs |

There are no records on the server to enumerate, so ID-guessing attacks have nothing to reach. Chat
sessions are keyed by a random, unguessable id, bounded in number and expire (`SESSION_*` settings).

## 3. Protecting data
- HTTPS only (Cloud Run); HSTS sent when the request arrived over HTTPS.
- Secrets in environment variables locally and Secret Manager in production; never in the repo,
  browser code or logs (`config.py: Settings` uses `SecretStr`).
- Data minimisation: coordinates are rounded to ~1 km before caching, logging or prompting; health
  sensitivities stay in the browser unless the user types them into chat.
- Retention: the server stores nothing about a person beyond bounded, expiring in-memory caches and
  chat sessions. Users delete their profile with "Clear my data" in settings.

## 4. Inputs and APIs
- Every request validated server-side with pydantic models (`extra="forbid"`, bounded fields).
- No database, no SQL, no shell commands built from input.
- Rate limiting on every `/api/` route (`core/middleware.py: RateLimitMiddleware`), body-size limit
  (`BodySizeLimitMiddleware`).
- CORS: not enabled — the UI is served from the same origin, so browsers block cross-origin calls by
  default. If CORS is ever added it must be an explicit allow-list, never `*`.
- No prices, payments or permission flags exist; nothing security-relevant is trusted from the browser.

## 5. AI features
- **AI output is untrusted.** The UI inserts it with `textContent` only — never `innerHTML`, never run as
  code (the repo audit fails on HTML-injection sinks in `static/js`).
- **AI keys stay on the server.** The browser only talks to our API.
- **Prompt injection is expected.** User text is masked, checked, and wrapped in untrusted-input tags;
  the system prompt carries a canary that is blocked if it ever appears in output.
- **Usage caps per client:** per minute and per day for every Gemini-backed feature
  (`AI_LIMIT_PER_MIN`, `AI_LIMIT_PER_DAY`; `core/rate_limit.py: DailyQuota`). The deterministic path keeps
  working when a cap is reached.
- **Spending alert** set on the Google Cloud billing account before deployment.
- **"I don't know" is allowed.** Every number must come from the engine or the Air Quality API; the
  assistant says it cannot answer rather than guess. Health questions get exposure guidance only; red-flag
  symptoms get "seek medical care now" first.
- The chat input shows a hint: do not enter ID numbers, phone numbers or addresses. They are masked anyway.

## 6. Logging and monitoring
Structured JSON logs with request id, route, status, latency, data mode, model id, prompt version,
grounding result and fallback flag. Never logged: user text, prompts, keys, exact coordinates.
Rate-limit and quota rejections are logged by code so they can be alerted on in Cloud Logging.

## 7. Compliance (India)
| Requirement | Applies? | How it's handled |
|---|---|---|
| DPDP Act 2023 — consent, purpose limits, deletion | Partly | No account; profile stored on the user's device with an explanation on first run; "Clear my data" deletes it; server keeps no personal data. |
| Health data rules | Partly | Optional sensitivity flags stay on the device; no diagnosis or treatment advice. |
| Data residency | No | No personal data stored server-side; region `asia-south1` used anyway. |
| Payments, children's accounts | No | No payments; no accounts. |

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
| R2, R11 | Limits are per Cloud Run instance (in memory) and reset on restart. | `--max-instances` caps total throughput; limits are bounded and tested. | Move limiter and quota to the Redis backend (`REDIS_URL`) if traffic grows. |

## 10. Pre-release gate
- [ ] Every rule met or listed in §9 with a fix plan.
- [ ] Dependency scan reviewed (`pip-audit` step in `scripts/gate.py`).
- [ ] Rate limit, AI quota and body limit confirmed on the deployed URL.
- [ ] `docs/SECURITY_AUDIT.md` completed with proof files.

---
Structure adapted from the *Vibecode Pre-Build Protocol* by Pankaj David
(https://github.com/PankajDavid/vibecode-prebuild-protocol), licensed CC BY 4.0.
