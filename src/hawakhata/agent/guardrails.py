"""Input and output guardrails for the HawaKhata conversational agent.

Implements L1 input sanitisation, prompt injection detection, PII masking,
health red-flag detection, and L2 output policy enforcement.
"""

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
    """Result of prompt injection analysis."""

    blocked: bool
    matched_rule_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PIIMaskResult:
    """Result of PII redaction."""

    masked_text: str
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthVerdict:
    """Result of health emergency/red-flag detection."""

    urgent: bool
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OutputPolicyVerdict:
    """Result of L2 output policy enforcement."""

    safe: bool
    sanitized_text: str
    blocked_reasons: list[str] = field(default_factory=list)


@functools.lru_cache(maxsize=1)
def _load_guardrails_config() -> dict[str, Any]:
    """Load and cache the guardrails configuration file."""
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
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = "".join(ch for ch in normalized if ch.isprintable() or ch in "\t\n\r")
    collapsed = re.sub(r"[ \t]+", " ", cleaned)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed).strip()
    return collapsed[:max_chars]


def detect_prompt_injection(text: str) -> InjectionVerdict:
    """Detect prompt injection and jailbreak patterns in user input."""
    cfg = _load_guardrails_config()
    patterns = cfg.get("injection_patterns", [])
    matched: list[str] = []

    for item in patterns:
        rule_id = item.get("id", "")
        regex = item.get("regex", "")
        if regex and re.search(regex, text):
            matched.append(rule_id)

    # Detect excessive delimiter runs
    if re.search(r"[-=_~*#]{30,}", text):
        matched.append("inj_delimiter_flood")

    return InjectionVerdict(blocked=len(matched) > 0, matched_rule_ids=matched)


def mask_pii(text: str) -> PIIMaskResult:
    """Redact Indian PII identifiers (phone, email, Aadhaar, PAN) with tags."""
    cfg = _load_guardrails_config()
    patterns = cfg.get("pii_patterns", [])
    result = text
    counts: dict[str, int] = {}

    for item in patterns:
        rule_id = item.get("id", "")
        regex = item.get("regex", "")
        mask = item.get("mask", "[PII]")
        if not regex:
            continue
        compiled = re.compile(regex)
        matches = len(compiled.findall(result))
        if matches > 0:
            counts[rule_id] = matches
            result = compiled.sub(mask, result)

    return PIIMaskResult(masked_text=result, counts=counts)


def detect_health_red_flags(text: str) -> HealthVerdict:
    """Detect acute respiratory distress or cardiac emergency red flags."""
    cfg = _load_guardrails_config()
    flags = cfg.get("health_red_flags", {})
    matched: list[str] = []
    text_lower = text.lower()

    for term in flags.get("en", []):
        if term.lower() in text_lower:
            matched.append(term)

    for term in flags.get("hi", []):
        if term in text:
            matched.append(term)

    return HealthVerdict(urgent=len(matched) > 0, matched_terms=matched)


def enforce_output_policy(
    reply: str,
    urgent: bool = False,
    canary: str | None = None,
    language: str = "en",
) -> OutputPolicyVerdict:
    """Check LLM output for canary leakage, diagnosis/dosing claims, and red flags."""
    if canary and canary in reply:
        return OutputPolicyVerdict(
            safe=False,
            sanitized_text="I cannot fulfill this request.",
            blocked_reasons=["canary_leak"],
        )

    cfg = _load_guardrails_config()
    blocklist = cfg.get("output_blocklist_patterns", [])
    sanitized = reply

    medical_disclaimer = (
        "[हवा खाता वायु प्रदूषण मार्गदर्शन प्रदान करता है, चिकित्सा निदान या उपचार नहीं। "
        "कृपया प्रमाणित चिकित्सक से परामर्श करें।]"
        if language == "hi"
        else (
            "[HawaKhata provides air pollution guidance, not medical diagnosis or treatment. "
            "Please consult a certified medical doctor.]"
        )
    )

    reasons: list[str] = []
    for item in blocklist:
        regex = item.get("regex", "")
        if regex and re.search(regex, sanitized):
            reasons.append(item.get("id", "disallowed_content"))
            sanitized = re.sub(regex, medical_disclaimer, sanitized)

    if urgent:
        emergency_prefix = (
            "⚠️ आपातकालीन चिकित्सा सूचना: इन लक्षणों के लिए तत्काल चिकित्सा मूल्यांकन की "
            "आवश्यकता है। कृपया आपातकालीन सेवाओं (भारत में 112 / 102 / 108) पर कॉल करें या "
            "तुरंत नजदीकी अस्पताल के आपातकालीन कक्ष में जाएँ।\n\n"
            if language == "hi"
            else (
                "⚠️ MEDICAL EMERGENCY NOTICE: These symptoms require immediate medical "
                "evaluation. Please call emergency services (112 / 102 / 108 in India) or visit "
                "the nearest hospital emergency room immediately.\n\n"
            )
        )
        sanitized = emergency_prefix + sanitized

    return OutputPolicyVerdict(
        safe=True,
        sanitized_text=sanitized,
        blocked_reasons=reasons,
    )
