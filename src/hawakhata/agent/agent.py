"""Ask HawaKhata conversational agent with tools, sessions, grounding gate, and fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from google.adk import Agent

from hawakhata.agent.fallback import (
    _dispatch_intent,
    detect_language,
    execute_fallback_turn,
    is_clock_comparison_query,
    route_intent,
)
from hawakhata.agent.grounding import check_numeric_grounding, extract_numbers
from hawakhata.agent.guardrails import (
    detect_health_red_flags,
    detect_prompt_injection,
    enforce_output_policy,
    mask_pii,
    sanitize_input,
)
from hawakhata.agent.prompts import render_prompt
from hawakhata.agent.sessions import SessionStore
from hawakhata.agent.tools import (
    ALL_TOOLS,
    ToolContext,
    get_smog_brief,
    reset_current_context,
    set_current_context,
)
from hawakhata.api.schemas import FamilyProfileInput, LocationInput
from hawakhata.core.logging import get_logger
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.integrations.gemini import GeminiCascadeClient

logger = get_logger(__name__)
CANARY_TOKEN = "HAWAKHATA_SEC_CANARY_7X9Q"  # noqa: S105


@dataclass(frozen=True)
class FollowUpQuestion:
    """Clarification question with suggestions."""

    question: str
    chips: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentTurnResult:
    """Complete grounded result of an agent turn."""

    reply: str
    language: str
    numbers_used: list[float]
    tool_calls: list[str]
    tool_outputs: list[Any]
    follow_up: FollowUpQuestion | None
    grounded: bool
    fallback_used: bool


def unwrap_agent_reply(text: str) -> str:
    """Extract and unwrap user-visible reply from raw LLM output."""
    if not text:
        return ""
    s = text.strip()
    fence_m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    candidate = fence_m.group(1).strip() if fence_m else s

    for target in (candidate, s):
        start, end = target.find("{"), target.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(target[start : end + 1])
                if isinstance(data, dict) and "reply" in data:
                    rep = data["reply"]
                    if isinstance(rep, str):
                        rep_str = rep.strip()
                        if rep_str.startswith("{") and '"reply"' in rep_str:
                            return unwrap_agent_reply(rep_str)
                        return rep_str
                    return str(rep)
            except Exception:
                pass

    rep_m = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', s)
    if rep_m:
        raw_val = rep_m.group(1)
        try:
            return str(bytes(raw_val, "utf-8").decode("unicode_escape"))
        except Exception:
            return raw_val

    if s.startswith("```") and s.endswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return s


class HawaKhataAgent:
    """Multi-turn ADK agent coordinating tools, grounding verification, and fallback."""

    def __init__(
        self, gemini_client: GeminiCascadeClient, session_store: SessionStore | None = None
    ) -> None:
        self.client = gemini_client
        self.sessions = session_store or SessionStore()
        self._adk_agent: Agent | None = None

    def _get_adk_agent(self, instruction: str) -> Agent:
        if self._adk_agent is None or self._adk_agent.instruction != instruction:
            self._adk_agent = Agent(
                name="hawakhata_agent",
                instruction=instruction,
                tools=ALL_TOOLS,
                model=self.client.primary_model,
            )
        return self._adk_agent

    def _resolve_follow_up(
        self, tool_outputs: list[Any], lang: str, user_text: str = ""
    ) -> FollowUpQuestion | None:
        if is_clock_comparison_query(user_text):
            return None
        for out in tool_outputs:
            if isinstance(out, dict) and out.get("missing_fields"):
                missing = out["missing_fields"]
                if "duration_min" in missing or "preferred_window" in missing:
                    q = (
                        "आप सैर या दौड़ कितने समय और किस समय करना चाहेंगे?"
                        if lang == "hi"
                        else "What duration and time window would you prefer?"
                    )
                    chips = (
                        ["30 मिनट, सुबह 7-8 बजे", "45 मिनट, दोपहर 1-2 बजे", "शाम को घर के अंदर"]
                        if lang == "hi"
                        else ["30 mins, 7-8 AM", "45 mins, 1-2 PM", "Indoor evening"]
                    )
                    return FollowUpQuestion(question=q, chips=chips)
        return None

    async def _execute_turn_body(
        self,
        safe_input: str,
        lang: str,
        session_id: str,
        *,
        profile: FamilyProfileInput,
        location: LocationInput,
        aq_client: AirQualityClient,
        client_ip: str,
        date_iso: str,
    ) -> tuple[str, list[str], list[Any], bool]:
        if not self.client.is_configured or is_clock_comparison_query(safe_input):
            fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
            return fb["reply"], [fb["tool_name"]], [fb["tool_output"]], True

        lang_label = "Hindi (Devanagari script)" if lang == "hi" else "English"
        sys_prompt = render_prompt("agent_system", CANARY=CANARY_TOKEN, LANGUAGE=lang_label)
        self._get_adk_agent(sys_prompt)

        try:
            brief_tool = await get_smog_brief()
            tool_outputs: list[Any] = [brief_tool]
            tool_calls = ["get_smog_brief"]

            intent, _ = route_intent(safe_input)
            if intent not in ("brief", "mask"):
                _, intent_tool_name, intent_tool_out = await _dispatch_intent(
                    intent,
                    lang,
                    location.city_name or "your area",
                    date_iso,
                    user_text=safe_input,
                    profile=profile,
                    aq_client=aq_client,
                    location=location,
                )
                tool_calls.append(intent_tool_name)
                tool_outputs.append(intent_tool_out)

            facts = dict(brief_tool.get("result", {}))
            city = location.city_name or "your area"
            facts["city"] = city
            for out in tool_outputs:
                if isinstance(out, dict) and "result" in out and isinstance(out["result"], dict):
                    facts.update(out["result"])
            facts_str = json.dumps(facts)
            history_entries = self.sessions.get_history(session_id)[-4:]
            hist_str = "\n".join(f"{h['role']}: {h['content']}" for h in history_entries)

            prompt = (
                f"<verified_engine_facts>\n{facts_str}\n</verified_engine_facts>\n"
                f"The user is located in {city}.\n"
                f"<conversation_history>\n{hist_str}\n</conversation_history>\n"
                f"<untrusted_user_input>\n{safe_input}\n</untrusted_user_input>"
            )

            llm_resp = await self.client.generate_content(
                prompt=prompt, system_instruction=sys_prompt, client_id=client_ip
            )
            reply = unwrap_agent_reply(llm_resp.text.strip())

            if not reply.strip():
                logger.info("Empty reply from Gemini; falling back to deterministic.")
                raise ValueError("Empty Gemini reply")

            if check_numeric_grounding(reply, tool_outputs, user_text=safe_input).passed:
                return reply, tool_calls, tool_outputs, False
            logger.info("Live Gemini reply ungrounded; falling back to deterministic.")
        except Exception as exc:
            logger.debug("Gemini live execution fallback: %s", exc)
        fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
        return fb["reply"], [fb["tool_name"]], [fb["tool_output"]], True

    async def run_turn(
        self,
        session_id: str,
        user_message: str,
        *,
        profile: FamilyProfileInput,
        location: LocationInput,
        aq_client: AirQualityClient,
        client_ip: str = "127.0.0.1",
        date_iso: str = "2026-11-18",
    ) -> AgentTurnResult:
        """Run an end-to-end conversation turn through guardrails, tools, and grounding."""
        cleaned = sanitize_input(user_message)
        lang = detect_language(cleaned)

        if detect_prompt_injection(cleaned).blocked:
            refusal = (
                "अनुरोध अस्वीकृत: मैं इस निर्देश को पूरा नहीं कर सकता।"
                if lang == "hi"
                else "Request blocked: I cannot fulfill instructions overriding safety rules."
            )
            return AgentTurnResult(refusal, lang, [], [], [], None, True, False)

        safe_input = mask_pii(cleaned).masked_text
        health = detect_health_red_flags(safe_input)

        token = set_current_context(ToolContext(profile, location, aq_client, date_iso))
        try:
            reply_text, tool_calls, tool_outputs, fb_used = await self._execute_turn_body(
                safe_input,
                lang,
                session_id,
                profile=profile,
                location=location,
                aq_client=aq_client,
                client_ip=client_ip,
                date_iso=date_iso,
            )
            out_v = enforce_output_policy(
                reply_text, urgent=health.urgent, canary=CANARY_TOKEN, language=lang
            )
            final_reply = out_v.sanitized_text
            canary_detected = (
                not out_v.safe
                or "canary_leak" in out_v.blocked_reasons
                or CANARY_TOKEN.lower() in reply_text.lower()
                or "canary_7x9q" in reply_text.lower()
                or CANARY_TOKEN.lower() in final_reply.lower()
                or "canary_7x9q" in final_reply.lower()
            )
            if canary_detected:
                logger.warning(
                    "Security event: Canary token leak detected in model output. Discarding reply and falling back."
                )
                fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
                final_reply = fb["reply"]
                tool_calls = [fb["tool_name"]]
                tool_outputs = [fb["tool_output"]]
                fb_used = True
            elif not final_reply.strip():
                logger.info("Empty final_reply after output policy; using deterministic fallback.")
                fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
                final_reply = fb["reply"]
                tool_calls = [fb["tool_name"]]
                tool_outputs = [fb["tool_output"]]
                fb_used = True

            # Final sanitize to guarantee zero canary substring reaches response
            if "canary_7x9q" in final_reply.lower() or CANARY_TOKEN.lower() in final_reply.lower():
                final_reply = re.sub(
                    r"(?i)<*HAWAKHATA_SEC_CANARY_[A-Z0-9]+>*", "", final_reply
                ).strip()
            nums = [n.value for n in extract_numbers(final_reply)]
            self.sessions.add_message(session_id, "user", user_message)
            self.sessions.add_message(session_id, "model", final_reply)
            return AgentTurnResult(
                final_reply,
                lang,
                nums,
                tool_calls,
                tool_outputs,
                self._resolve_follow_up(tool_outputs, lang, safe_input),
                True,
                fb_used,
            )
        finally:
            reset_current_context(token)
