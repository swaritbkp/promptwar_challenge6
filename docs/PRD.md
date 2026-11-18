# PRD — HawaKhata (Air Passbook)

## Problem Statement & Feature Mapping
| Brief Clause | Feature | Module & Function |
|---|---|---|
| GenAI-powered assistant | F5 Ask HawaKhata | `agent/agent.py: HawaKhataAgent`, `agent/tools.py` |
| Helps families | Per-member passbook | `engine/dose.py: compute_member_dose()` |
| Communities | Mohalla multiplier | `engine/swaps.py: scale_to_community()` |
| Severe winter smog | NAQI & diurnal alerting | `engine/aqi.py`, `services/brief_service.py` |
| Low-emission routines | F2 Clean-Window Planner | `engine/planner.py: optimise_day_plan()` |
| Indoor air hacks | F3 Indoor Simulator | `engine/indoor_model.py: simulate_indoor_pm25()` |
| Sustainable alternatives | F4 Swap Simulator | `engine/emissions.py`, `engine/swaps.py` |
| Tailored to location | Google AQ API | `integrations/air_quality.py` |
| Tailored to lifestyle | Family profile | `api/schemas.py: FamilyProfileInput` |
| Clearly explaining impact | Explanations & Trust | `engine/budget.py`, `engine/explain.py` |

## Core Features & Acceptance Criteria
- **F1 Family Air Passbook:** Per member `debit_ug`, `budget_ug`, `balance_ug`, `overspend_ratio`, `cigarette_equivalent`. Debit ≥ 0; budget scales with inhalation volume; full explanation object with formulas and citations.
- **F2 Clean-Window Planner:** Inputs fixed commitments and flexible activities. Combinatorial search over forecast series with Monte Carlo uncertainty. Never moves fixed blocks; never overlaps same member activities; deterministic given seed.
- **F3 Indoor Air Simulator:** Single-zone mass balance per room with exact exponential stepping. Windows, purifiers, cooking, heating events. Monotonic: purifier never increases PM2.5; sources never decrease PM2.5. Purifier sizing against target ACH.
- **F4 Swap Simulator & Mohalla:** Catalog of swaps from `constants.v1.json`. Outputs Δ breathe (µg avoided) and Δ emit (g PM2.5, kg CO₂ avoided). Community scaling: households × adoption rate.
- **F5 Ask HawaKhata Agent:** Multi-turn session memory, tool calling, grounding gate enforcement (zero LLM math), L1/L2 guardrails (injection, PII, canary, health boundaries), deterministic fallback without Gemini.
- **F6 Proactive Smog Brief:** Morning summary with worst hour, cleanest window, sensitive member alerts, top 3 actions, and automatic re-planning on forecast shifts exceeding threshold.
- **F7 Story Mode:** Guided reproducible tour (`/?story=ncr|chd`) with fixed clock and demo data from `story.v1.json`. Identical numbers across runs; keyboard controls; screen reader accessible.
- **F8 Onboarding & How-It-Works:** ≤ 60s 3-step setup (or 1-tap demo family). Trust page with architecture SVG, verified constants table, and privacy statement.

## Non-Functional Boundaries
- Zero LLM math: "Gemini proposes, code decides".
- Strict privacy: Coordinates rounded to ~1 km; health sensitivities stay local in browser; PII masked.
- Sub-second deterministic fallback; fixture fallback when Google API is offline or unkeyed.
