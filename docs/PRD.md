# PRD — HawaKhata (Air Passbook)

## Problem Statement & Feature Mapping
| Clause | Feature | Engine Citation |
|---|---|---|
| GenAI assistant | F5 Ask HawaKhata | `agent/agent.py: HawaKhataAgent()` |
| Families | Passbook | `engine/dose.py: compute_member_dose()` |
| Communities | Mohalla multiplier | `engine/swaps.py: scale_to_community()` |
| Winter smog | NAQI & diurnal alerts | `engine/aqi.py: pm25_to_naqi_category()` |
| Low-emission routines | F2 Planner | `engine/planner.py: optimise_day_plan()` |
| Indoor hacks | F3 Indoor Simulator | `engine/indoor_model.py: simulate_indoor_pm25()` |
| Sustainable alternatives | F4 Swaps | `engine/swaps.py: evaluate_swap()` |
| Explaining impact | Trust & formulas | `engine/budget.py: daily_air_budget_ug()` |

## Core Features
- **F1 Family Passbook:** Per member debit, budget, balance, cigarette equivalence (WHO 2021).
- **F2 Clean-Window Planner:** Combinatorial search avoiding peaks; preserves fixed blocks.
- **F3 Indoor Air Simulator:** Single-zone ODE model; purifier sizing (5 ACH target).
- **F4 Swaps & Mohalla:** Household deltas & neighborhood community multiplier.
- **F5 Ask HawaKhata Agent:** Multi-turn grounded assistant (EN/HI); L1/L2 guardrails; fallback.
- **F6 Proactive Smog Brief:** Morning brief with cleanest window & auto-replan on shifts.
- **F7 Story Mode:** Guided tour (`/?story=ncr|chd`) with fixed clock and demo fixtures.
- **F8 Onboarding & Trust:** Accessible setup & How-it-works page.

## Non-Functional Boundaries
- Zero LLM math: "Gemini proposes, code decides".
- Privacy: Coordinates rounded (~1 km); health data local; PII masked.
- Sub-second deterministic fallback without API keys.
