---
name: narrator
version: v1.0
purpose: Optional prose for deterministic endpoints (passbook, plan, indoor, swaps, brief)
---

Write a short explanation (max 4 sentences, language: {{LANGUAGE}}) of the result JSON below for a family.
Rules: use only numbers present in the JSON (round as they appear); name the member and the action; say
what changes in their passbook; no medical advice; no new facts. If the result says the usual schedule is
already optimal, say so plainly.

<result_json>
{{RESULT_JSON}}
</result_json>
