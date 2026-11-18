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
| D10 | External API facts | Filled in FND-01 with docs URL + date + versions | Never build on guessed API shapes. | Pending |
