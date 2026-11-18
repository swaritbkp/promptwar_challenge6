# Prompt changelog

## v1.0 — initial
- agent_system: tool-first, single follow-up, mitigation hierarchy, health boundary, untrusted-input tags, canary.
- narrator: numbers-only-from-JSON explanation for deterministic endpoints.
- planner: free text → structured activities with missing_fields; no time suggestions by the LLM.

Rule: any wording change bumps the version folder (v1.1 …), updates this file, and re-runs `eval/run_eval.py`.
