"""Input and output guardrails for the HawaKhata conversational agent."""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
GUARDRAILS_CONFIG_PATH = ROOT / "data" / "guardrails.v1.json"


@dataclass(frozen=True)
class InjectionVerdict:
    """Verdict of prompt injection check."""

    blocked: bool
    matched_rule_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PIIMaskResult:
    """Result of PII redaction."""

    masked_text: str
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthVerdict:
    """Result of health emergency check."""

    urgent: bool
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OutputPolicyVerdict:
    """Result of L2 output policy check."""

    safe: bool
    sanitized_text: str
    blocked_reasons: list[str] = field(default_factory=list)


@functools.lru_cache(maxsize=1)
def _load_guardrails_config() -> dict[str, Any]:
    if not GUARDRAILS_CONFIG_PATH.exists():
        return {
            "injection_patterns": [],
            "pii_patterns": [],
            "health_red_flags": {"en": [], "hi": []},
            "output_blocklist_patterns": [],
        }
    return json.loads(GUARDRAILS_CONFIG_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def sanitize_input(text: str, max_chars: int = 1000) -> str:
    """Normalize unicode, strip control characters, and cap input length."""
    norm = unicodedata.normalize("NFKC", text)
    cleaned = "".join(ch for ch in norm if ch.isprintable() or ch in "\t\n\r")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", cleaned)).strip()[:max_chars]


def detect_prompt_injection(text: str) -> InjectionVerdict:
    """Detect prompt injection and jailbreak patterns in user input."""
    matched = [
        item.get("id", "")
        for item in _load_guardrails_config().get("injection_patterns", [])
        if item.get("regex") and re.search(item["regex"], text)
    ]
    if re.search(r"[-=_~*#]{30,}", text):
        matched.append("inj_delimiter_flood")
    return InjectionVerdict(blocked=len(matched) > 0, matched_rule_ids=matched)


def mask_pii(text: str) -> PIIMaskResult:
    """Redact Indian PII identifiers (phone, email, Aadhaar, PAN) with tags."""
    result = text
    counts: dict[str, int] = {}
    for item in _load_guardrails_config().get("pii_patterns", []):
        r_id, rgx, mask = item.get("id", ""), item.get("regex", ""), item.get("mask", "[PII]")
        if rgx:
            comp = re.compile(rgx)
            m = len(comp.findall(result))
            if m > 0:
                counts[r_id] = m
                result = comp.sub(mask, result)
    return PIIMaskResult(masked_text=result, counts=counts)


def detect_health_red_flags(text: str) -> HealthVerdict:
    """Detect acute respiratory distress or cardiac emergency red flags."""
    flags = _load_guardrails_config().get("health_red_flags", {})
    t_low = text.lower()
    matched = [t for t in flags.get("en", []) if t.lower() in t_low] + [
        t for t in flags.get("hi", []) if t in text
    ]
    return HealthVerdict(urgent=len(matched) > 0, matched_terms=matched)


def enforce_output_policy(
    reply: str, urgent: bool = False, canary: str | None = None, language: str = "en"
) -> OutputPolicyVerdict:
    """Check LLM output for canary leakage, diagnosis/dosing claims, and red flags."""
    if canary and canary in reply:
        return OutputPolicyVerdict(
            safe=False,
            sanitized_text="I cannot fulfill this request.",
            blocked_reasons=["canary_leak"],
        )

    blocklist = _load_guardrails_config().get("output_blocklist_patterns", [])
    sanitized = reply
    disclaimer = (
        "[हवा खाता वायु प्रदूषण मार्गदर्शन प्रदान करता है, चिकित्सा निदान नहीं। कृपया चिकित्सक से परामर्श करें।]"
        if language == "hi"
        else "[HawaKhata provides air pollution guidance, not medical diagnosis or treatment. Please consult a certified medical doctor.]"
    )
    reasons: list[str] = []
    for item in blocklist:
        rgx = item.get("regex", "")
        if rgx and re.search(rgx, sanitized):
            reasons.append(item.get("id", "disallowed_content"))
            sanitized = re.sub(rgx, disclaimer, sanitized)

    if urgent:
        prefix = (
            "⚠️ आपातकालीन चिकित्सा सूचना: इन लक्षणों के लिए तत्काल चिकित्सा मूल्यांकन की आवश्यकता है। कृपया आपातकालीन सेवाओं (112 / 102 / 108) पर कॉल करें या अस्पताल जाएँ।\n\n"
            if language == "hi"
            else "⚠️ MEDICAL EMERGENCY NOTICE: These symptoms require immediate medical evaluation. Call emergency services (112 / 102 / 108) or visit ER immediately.\n\n"
        )
        sanitized = prefix + sanitized

    return OutputPolicyVerdict(safe=True, sanitized_text=sanitized, blocked_reasons=reasons)
