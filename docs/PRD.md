# PRD — HawaKhata (Air Passbook)

## Problem Statement & Feature Mapping
| Brief Clause | Feature | Engine & Module Citation |
|---|---|---|
| GenAI-powered assistant | F5 Ask HawaKhata | `agent/agent.py: HawaKhataAgent()`, `agent/tools.py` |
| Helps families | Per-member passbook | `engine/dose.py: compute_member_dose()` |
| Communities | Mohalla multiplier | `engine/swaps.py: scale_to_community()` |
| Severe winter smog | NAQI & diurnal alerting | `engine/aqi.py: pm25_to_naqi_category()`, `services/brief_service.py` |
| Low-emission routines | F2 Clean-Window Planner | `engine/planner.py: optimise_day_plan()` |
| Indoor air hacks | F3 Indoor Simulator | `engine/indoor_model.py: simulate_indoor_pm25()` |
| Sustainable alternatives | F4 Swap Simulator | `engine/swaps.py: evaluate_swap()` |
| Clearly explaining impact | Explanations & Trust | `engine/budget.py: daily_air_budget_ug()`, `engine/explain.py` |

## Core Features & Acceptance Criteria
- **F1 Family Air Passbook:** Per member `debit_ug`, `budget_ug`, `balance_ug`, `cigarette_equivalent`. WHO 2021 air budget and Berkeley Earth cigarette equivalence.
- **F2 Clean-Window Planner:** Combinatorial search over forecast series with Monte Carlo uncertainty. Preserves fixed blocks; eliminates activity overlaps.
- **F3 Indoor Air Simulator:** Single-zone mass-balance differential equation with exact exponential stepping. Purifier sizing against 5 ACH target.
- **F4 Swap Simulator & Mohalla:** Household emission and dose deltas; linear neighborhood community multiplier (households × participation).
- **F5 Ask HawaKhata Agent:** Multi-turn session memory, tool calling, grounding gate enforcement (zero LLM math), L1/L2 guardrails, deterministic fallback.
- **F6 Proactive Smog Brief:** Morning summary with worst hour, cleanest window, sensitive member alerts, and automatic re-planning on forecast shifts.
- **F7 Story Mode:** Guided reproducible tour (`/?story=ncr|chd`) with fixed clock and demo fixtures. Screen reader accessible.
- **F8 Onboarding & How-It-Works:** Accessible setup; trust page with architecture, formulas, and privacy statement.

## Non-Functional Boundaries
- Zero LLM math: "Gemini proposes, code decides".
- Strict privacy: Coordinates rounded to ~1 km; health sensitivities stay local; PII masked.
- Sub-second deterministic fallback without API keys.
