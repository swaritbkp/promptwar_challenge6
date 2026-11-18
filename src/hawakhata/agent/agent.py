"""Ask HawaKhata conversational agent with tools, sessions, grounding gate, and fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google.adk import Agent

from hawakhata.agent.fallback import detect_language, execute_fallback_turn
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
    reset_current_context,
    set_current_context,
)
from hawakhata.api.schemas import FamilyProfileInput, LocationInput
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.integrations.gemini import GeminiCascadeClient

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


class HawaKhataAgent:
    """Multi-turn ADK agent coordinating tools, grounding verification, and fallback."""

    def __init__(
        self,
        gemini_client: GeminiCascadeClient,
        session_store: SessionStore | None = None,
    ) -> None:
        """Initialize HawaKhataAgent with Gemini cascade client and session store."""
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

    def _resolve_follow_up(self, tool_outputs: list[Any], lang: str) -> FollowUpQuestion | None:
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
        *,
        profile: FamilyProfileInput,
        location: LocationInput,
        aq_client: AirQualityClient,
        client_ip: str,
        date_iso: str,
    ) -> tuple[str, list[str], list[Any], bool]:
        if not self.client.is_configured:
            fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
            return fb["reply"], [fb["tool_name"]], [fb["tool_output"]], True

        lang_label = "Hindi (Devanagari script)" if lang == "hi" else "English"
        sys_prompt = render_prompt("agent_system", CANARY=CANARY_TOKEN, LANGUAGE=lang_label)
        self._get_adk_agent(sys_prompt)

        try:
            llm_resp = await self.client.generate_content(
                prompt=f"<untrusted_user_input>\n{safe_input}\n</untrusted_user_input>",
                system_instruction=sys_prompt,
                client_id=client_ip,
            )
            reply = llm_resp.text.strip()
            tool_outputs: list[Any] = []
            if not check_numeric_grounding(reply, tool_outputs).passed:
                fb = await execute_fallback_turn(safe_input, profile, location, aq_client, date_iso)
                return fb["reply"], [fb["tool_name"]], [fb["tool_output"]], True
            return reply, [], tool_outputs, False
        except Exception:
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
            nums = [n.value for n in extract_numbers(final_reply)]

            self.sessions.add_message(session_id, "user", user_message)
            self.sessions.add_message(session_id, "model", final_reply)

            return AgentTurnResult(
                final_reply,
                lang,
                nums,
                tool_calls,
                tool_outputs,
                self._resolve_follow_up(tool_outputs, lang),
                True,
                fb_used,
            )
        finally:
            reset_current_context(token)
