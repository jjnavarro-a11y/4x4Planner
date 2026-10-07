# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runner-wide safety guardrail and audit plugins (`BasePlugin`) for the 4x4 Planner."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import BaseModel

from app.app_utils.telemetry import (
    PiiRedactor,
    intent_outcome_tracker,
    redact_pii_text,
)

logger = logging.getLogger(__name__)

_SAFE_PROMPT_STATE_KEY = "is_user_prompt_safe"
_UNSAFE_REASON_STATE_KEY = "unsafe_prompt_reason"

_UNSAFE_PROMPT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt\s+override|bypass\s+safety\s+guardrails)\b",
            re.IGNORECASE,
        ),
        "Prompt injection / guardrail bypass attempt detected.",
    ),
    (
        re.compile(
            r"\b(cut\s+(the\s+)?lock|bypass\s+(locked\s+)?gate|drive\s+around\s+locked\s+gate|"
            r"enter\s+designated\s+wilderness\s+illegally|poach\s+closed\s+trail)\b",
            re.IGNORECASE,
        ),
        "Illegal motorized trespass or closed-gate bypass request blocked by Tread Lightly! policy.",
    ),
]

_SAFETY_BLOCK_MESSAGE = (
    "I cannot assist with bypassing safety guardrails, entering closed/locked "
    "areas, or driving motorized vehicles in prohibited wilderness zones. "
    "I can help you plan legal, Tread Lightly!-compliant 4x4 routes instead."
)


class OffroadSafetyGuardrailPlugin(BasePlugin):
    """Runner-wide safety guardrail, PII redaction, and intent-vs-outcome audit plugin.

    Implements:
    1. Two-phase session-poisoning defense (`on_user_message_callback` +
       `before_run_callback`) so unsafe prompts are rejected before poisoning
       conversational session state.
    2. Automatic PII redaction on incoming user messages, tool arguments/outputs,
       and LLM responses (`PiiRedactor`).
    3. Structured Intent vs. Outcome capture (`IntentOutcomeTracker`) across
       agent, model, and tool lifecycle hooks.
    4. Automatic normalization of strict Pydantic `BaseModel` tool return models
       into JSON-compatible dictionaries for ADK `FunctionResponse` serialization.
    """

    def __init__(self, name: str = "offroad_safety_guardrail_plugin") -> None:
        super().__init__(name=name)

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Inspects and sanitizes user messages before they are appended to session history."""
        if not user_message or not user_message.parts:
            invocation_context.session.state[_SAFE_PROMPT_STATE_KEY] = True
            return None

        first_part = user_message.parts[0]
        raw_text = getattr(first_part, "text", None)
        if not raw_text:
            invocation_context.session.state[_SAFE_PROMPT_STATE_KEY] = True
            return None

        # 1. Check for prompt injection or illegal off-road trespass requests
        for pattern, reason in _UNSAFE_PROMPT_PATTERNS:
            if pattern.search(raw_text):
                invocation_context.session.state[_SAFE_PROMPT_STATE_KEY] = False
                invocation_context.session.state[_UNSAFE_REASON_STATE_KEY] = reason
                intent_outcome_tracker.record_intent(
                    invocation_id=invocation_context.invocation_id,
                    session_id=invocation_context.session.id,
                    actor="user_message_guardrail",
                    stage="user_prompt",
                    declared_intent="Evaluate incoming user prompt against off-road safety policy",
                    raw_inputs={"prompt_preview": raw_text[:120]},
                )
                intent_outcome_tracker.record_outcome(
                    invocation_id=invocation_context.invocation_id,
                    session_id=invocation_context.session.id,
                    actor="user_message_guardrail",
                    stage="user_prompt",
                    status="blocked_by_guardrail",
                    intent_fulfilled=False,
                    actual_outcome_summary=reason,
                    safety_verdict="BLOCKED_UNSAFE_PROMPT",
                    discrepancy_reason=reason,
                )
                return types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="[REDACTED UNSAFE OFF-ROAD OR INJECTION REQUEST]"
                        )
                    ],
                )

        invocation_context.session.state[_SAFE_PROMPT_STATE_KEY] = True
        invocation_context.session.state[_UNSAFE_REASON_STATE_KEY] = ""

        # 2. Redact any PII from user message before storing in session history
        redacted_text = redact_pii_text(raw_text)
        if redacted_text != raw_text:
            updated_parts = list(user_message.parts)
            updated_parts[0] = types.Part.from_text(text=redacted_text)
            return types.Content(role=user_message.role, parts=updated_parts)

        return None

    async def before_run_callback(
        self,
        *,
        invocation_context: InvocationContext,
    ) -> types.Content | None:
        """Halts execution if `on_user_message_callback` flagged the prompt as unsafe."""
        is_safe = invocation_context.session.state.get(_SAFE_PROMPT_STATE_KEY, True)
        if not is_safe:
            invocation_context.session.state[_SAFE_PROMPT_STATE_KEY] = True
            return types.Content(
                role="model",
                parts=[types.Part.from_text(text=_SAFETY_BLOCK_MESSAGE)],
            )
        return None

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        """Records agent-level execution intent before an agent starts."""
        intent_outcome_tracker.record_intent(
            invocation_id=callback_context.invocation_id,
            session_id=callback_context.session.id,
            actor=agent.name,
            stage="agent",
            declared_intent=f"Execute agent '{agent.name}' orchestration step",
            raw_inputs={"agent_name": agent.name},
        )
        return None

    async def after_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        """Pairs agent outcome with the recorded agent intent."""
        intent_outcome_tracker.record_outcome(
            invocation_id=callback_context.invocation_id,
            session_id=callback_context.session.id,
            actor=agent.name,
            stage="agent",
            status="success",
            intent_fulfilled=True,
            actual_outcome_summary=f"Agent '{agent.name}' completed turn successfully.",
            safety_verdict="PASS",
        )
        return None

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        """Records model call intent prior to LLM invocation."""
        model_name = getattr(llm_request, "model", None) or "default_model"
        intent_outcome_tracker.record_intent(
            invocation_id=callback_context.invocation_id,
            session_id=callback_context.session.id,
            actor=callback_context.agent_name,
            stage="model",
            declared_intent=f"Generate LLM response using '{model_name}' for '{callback_context.agent_name}'",
            raw_inputs={
                "agent_name": callback_context.agent_name,
                "model": str(model_name),
            },
        )
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Redacts residual PII from LLM output and records model outcome."""
        summary = "LLM response generated"
        if llm_response.content and llm_response.content.parts:
            new_parts: list[types.Part] = []
            modified = False
            for part in llm_response.content.parts:
                if getattr(part, "text", None):
                    redacted = redact_pii_text(part.text or "")
                    if redacted != part.text:
                        modified = True
                        new_parts.append(types.Part.from_text(text=redacted))
                    else:
                        new_parts.append(part)
                    summary = redacted[:160]
                elif getattr(part, "function_call", None):
                    fc_name = getattr(part.function_call, "name", "tool_call")
                    summary = f"Requested tool call: {fc_name}"
                    new_parts.append(part)
                else:
                    new_parts.append(part)
            if modified:
                llm_response.content.parts = new_parts

        intent_outcome_tracker.record_outcome(
            invocation_id=callback_context.invocation_id,
            session_id=callback_context.session.id,
            actor=callback_context.agent_name,
            stage="model",
            status="success",
            intent_fulfilled=True,
            actual_outcome_summary=summary,
            safety_verdict="PASS",
        )
        return None

    async def on_model_error_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
        error: Exception,
    ) -> LlmResponse | None:
        """Records model failure outcome in structured audit log."""
        intent_outcome_tracker.record_outcome(
            invocation_id=callback_context.invocation_id,
            session_id=callback_context.session.id,
            actor=callback_context.agent_name,
            stage="model",
            status="error",
            intent_fulfilled=False,
            actual_outcome_summary=f"LLM invocation failed for {callback_context.agent_name}",
            safety_verdict="ERROR",
            discrepancy_reason=str(error),
        )
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Sanitizes tool arguments and logs tool invocation intent."""
        sanitized_args = PiiRedactor.redact_structure(tool_args)
        intent_outcome_tracker.record_intent(
            invocation_id=tool_context.invocation_id,
            session_id=tool_context.session.id,
            actor=tool.name,
            stage="tool",
            declared_intent=f"Invoke tool '{tool.name}' with validated parameters",
            raw_inputs=sanitized_args,
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any] | BaseModel | Any,
    ) -> dict[str, Any] | None:
        """Normalizes strict Pydantic tool output models to dict, scrubs PII, and logs outcome."""
        normalized_dict: dict[str, Any] | None = None
        if isinstance(result, BaseModel):
            normalized_dict = result.model_dump(mode="json")
        elif isinstance(result, dict):
            normalized_dict = result

        status: Literal["success", "blocked_by_guardrail", "error", "pending_hitl"] = (
            "success"
        )
        intent_fulfilled = True
        safety_verdict = "PASS"
        discrepancy: str | None = None
        summary = f"Tool '{tool.name}' succeeded"

        if isinstance(normalized_dict, dict):
            raw_status = str(normalized_dict.get("status", "success"))
            verdict = str(normalized_dict.get("verdict", "PASS"))
            if verdict == "REJECTED_UNSAFE_FOR_RIG":
                status = "blocked_by_guardrail"
                intent_fulfilled = False
                safety_verdict = verdict
                discrepancy = (
                    "; ".join(normalized_dict.get("blocking_reasons", []))
                    or "Trail rejected due to rig capability mismatch."
                )
            elif raw_status == "pending_human_confirmation":
                status = "pending_hitl"
                intent_fulfilled = False
                safety_verdict = "PENDING_HITL_CONFIRMATION"
                discrepancy = (
                    "High-risk backcountry dispatch paused for human confirmation."
                )
            elif raw_status in {"error", "rejected"}:
                status = "error"
                intent_fulfilled = False
                safety_verdict = raw_status.upper()
                discrepancy = str(normalized_dict.get("advisory") or raw_status)

            summary = str(
                normalized_dict.get("advisory")
                or normalized_dict.get("summary")
                or normalized_dict.get("verdict")
                or f"Tool '{tool.name}' returned status={raw_status}"
            )
            normalized_dict = PiiRedactor.redact_structure(normalized_dict)

        intent_outcome_tracker.record_outcome(
            invocation_id=tool_context.invocation_id,
            session_id=tool_context.session.id,
            actor=tool.name,
            stage="tool",
            status=status,
            intent_fulfilled=intent_fulfilled,
            actual_outcome_summary=summary,
            safety_verdict=safety_verdict,
            discrepancy_reason=discrepancy,
        )

        return normalized_dict

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> dict[str, Any] | None:
        """Records tool execution errors in the structured intent/outcome tracker."""
        intent_outcome_tracker.record_outcome(
            invocation_id=tool_context.invocation_id,
            session_id=tool_context.session.id,
            actor=tool.name,
            stage="tool",
            status="error",
            intent_fulfilled=False,
            actual_outcome_summary=f"Tool '{tool.name}' raised an exception",
            safety_verdict="ERROR",
            discrepancy_reason=str(error),
        )
        return None
