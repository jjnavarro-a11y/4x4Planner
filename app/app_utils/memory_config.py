# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared Vertex AI Memory Bank configuration and ADK session state lifecycle callbacks."""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from app.app_utils.telemetry import (
    PiiRedactor,
    audit_logger,
    intent_outcome_tracker,
)
from app.app_utils.typing import UserRigProfile

logger = logging.getLogger(__name__)

# --- Vertex AI Memory Bank Configuration ---
# Declares which managed and custom topics Memory Bank should extract and
# consolidate across user sessions on Agent Runtime and Cloud Run.
try:
    from vertexai._genai.types import (
        ManagedTopicEnum,
    )
    from vertexai._genai.types import (
        MemoryBankCustomizationConfig as CustomizationConfig,
    )
    from vertexai._genai.types import (
        MemoryBankCustomizationConfigMemoryTopic as MemoryTopic,
    )
    from vertexai._genai.types import (
        MemoryBankCustomizationConfigMemoryTopicCustomMemoryTopic as CustomMemoryTopic,
    )
    from vertexai._genai.types import (
        MemoryBankCustomizationConfigMemoryTopicManagedMemoryTopic as ManagedMemoryTopic,
    )
    from vertexai._genai.types import (
        ReasoningEngineContextSpecMemoryBankConfig as MemoryBankConfig,
    )

    memory_bank_config: Any = MemoryBankConfig(
        customization_configs=[
            CustomizationConfig(
                memory_topics=[
                    MemoryTopic(
                        managed_memory_topic=ManagedMemoryTopic(
                            managed_topic_enum=ManagedTopicEnum.USER_PERSONAL_INFO,
                        ),
                    ),
                    MemoryTopic(
                        managed_memory_topic=ManagedMemoryTopic(
                            managed_topic_enum=ManagedTopicEnum.USER_PREFERENCES,
                        ),
                    ),
                    MemoryTopic(
                        managed_memory_topic=ManagedMemoryTopic(
                            managed_topic_enum=ManagedTopicEnum.KEY_CONVERSATION_DETAILS,
                        ),
                    ),
                    MemoryTopic(
                        managed_memory_topic=ManagedMemoryTopic(
                            managed_topic_enum=ManagedTopicEnum.EXPLICIT_INSTRUCTIONS,
                        ),
                    ),
                    MemoryTopic(
                        custom_memory_topic=CustomMemoryTopic(
                            label="user_4x4_rig_profile",
                            description=(
                                "User's 4x4 vehicle build specifications including make/model, "
                                "tire diameter in inches, ground clearance in inches, 4WD Low "
                                "range transfer case (4Lo), locking differentials, winch, "
                                "fuel tank capacity, highway MPG, and solo vs group travel."
                            ),
                        ),
                    ),
                    MemoryTopic(
                        custom_memory_topic=CustomMemoryTopic(
                            label="past_trail_history",
                            description=(
                                "Previously planned or completed 4x4 trails, regions, "
                                "campsite preferences (BLM dispersed vs developed), and "
                                "rejected trails exceeding the user's rig capabilities."
                            ),
                        ),
                    ),
                ],
            ),
        ],
    )
except Exception:
    memory_bank_config = {
        "managed_topics": [
            "USER_PERSONAL_INFO",
            "USER_PREFERENCES",
            "KEY_CONVERSATION_DETAILS",
            "EXPLICIT_INSTRUCTIONS",
        ],
        "custom_topics": ["user_4x4_rig_profile", "past_trail_history"],
    }


def format_rig_profile_summary(profile_data: dict[str, Any] | UserRigProfile) -> str:
    """Formats a user rig profile dictionary or model into a concise instruction summary."""
    if isinstance(profile_data, UserRigProfile):
        p = profile_data.model_dump(mode="python")
    else:
        p = profile_data
    return (
        f"{p.get('vehicle_name', 'Stock 4WD (Assumed)')} | "
        f'Tires: {p.get("tire_size_inches", 31.0)}" | '
        f'Clearance: {p.get("clearance_inches", 9.5)}" | '
        f"4Lo: {p.get('has_4lo', True)} | "
        f"Lockers: {p.get('lockers', 0)} | "
        f"Winch: {p.get('has_winch', False)} | "
        f"MPG: {p.get('highway_mpg', 18.0)} | "
        f"Tank: {p.get('tank_capacity_gallons', 21.0)} gal | "
        f"Solo: {p.get('is_solo', True)} | "
        f"Max Safe Rating: {p.get('max_safe_difficulty', 4)}/10"
    )


async def initialize_overlanding_state(callback_context: CallbackContext) -> None:
    """Initializes scoped session state keys before agent execution (`before_agent_callback`).

    Ensures all template variables (`{user_rig_profile_summary}`, `{active_trip_region}`)
    exist in `callback_context.state` on the very first turn to prevent `KeyError` and
    records the start of the agent's turn for Intent-vs-Outcome auditing.
    """
    state = callback_context.state

    # 1. User-scoped persistent state (`user:` prefix persists across sessions)
    if "user:rig_profile" not in state:
        default_profile = UserRigProfile().model_dump(mode="json")
        state["user:rig_profile"] = default_profile

    if "user:preferred_camping_style" not in state:
        state["user:preferred_camping_style"] = (
            "Designated BLM/USFS dispersed or developed campgrounds"
        )

    # 2. App-scoped global metadata (`app:` prefix shared across users)
    if "app:safety_policy_version" not in state:
        state["app:safety_policy_version"] = "2026.10-strict-25pct-reserve"

    # 3. Session-scoped conversation state & template variables
    if "active_trip_region" not in state:
        state["active_trip_region"] = "Not yet selected (infer from user prompt)"

    state["user_rig_profile_summary"] = format_rig_profile_summary(
        state["user:rig_profile"]
    )

    if "intent_outcome_log" not in state:
        state["intent_outcome_log"] = []

    # 4. Invocation-scoped temporary state (`temp:` prefix cleared after turn)
    state["temp:turn_tool_calls"] = []

    user_text = ""
    if callback_context.user_content and callback_context.user_content.parts:
        user_text = " ".join(
            part.text or "" for part in callback_context.user_content.parts
        ).strip()
    clean_user_text, _ = PiiRedactor.redact_text(user_text)
    state["temp:current_turn_intent"] = (
        clean_user_text[:240]
        if clean_user_text
        else "Build a safe, rig-compatible 4x4 overlanding itinerary"
    )

    inv_id = getattr(callback_context, "invocation_id", "turn")
    session_id = getattr(getattr(callback_context, "session", None), "id", "session")
    intent_outcome_tracker.record_intent(
        invocation_id=str(inv_id),
        session_id=str(session_id),
        actor=callback_context.agent_name,
        stage="agent",
        declared_intent=state["temp:current_turn_intent"],
        raw_inputs={
            "active_trip_region": state["active_trip_region"],
            "rig_profile": state["user:rig_profile"],
        },
    )


async def generate_memories_callback(
    callback_context: CallbackContext,
) -> types.Content | None:
    """Persists session events to Vertex AI Memory Bank and logs turn outcome (`after_agent_callback`)."""
    state = callback_context.state
    inv_id = getattr(callback_context, "invocation_id", "turn")
    session_id = getattr(getattr(callback_context, "session", None), "id", "session")
    tools_called = state.get("temp:turn_tool_calls", [])

    # Trigger long-term memory consolidation in Memory Bank / InMemoryMemoryService
    memory_persisted = False
    try:
        await callback_context.add_session_to_memory()
        memory_persisted = True
    except Exception as exc:
        logger.debug(
            "Memory Bank consolidation skipped or unavailable in current runner: %s",
            type(exc).__name__,
        )

    audit_entry = intent_outcome_tracker.record_outcome(
        invocation_id=str(inv_id),
        session_id=str(session_id),
        actor=callback_context.agent_name,
        stage="agent",
        status="success",
        intent_fulfilled=True,
        safety_verdict="PASS",
        actual_outcome_summary=(
            f"Completed turn with tools={tools_called}; "
            f"memory_persisted={memory_persisted}; "
            f"rig_summary='{state.get('user_rig_profile_summary', '')}'"
        ),
        fallback_declared_intent=str(
            state.get(
                "temp:current_turn_intent",
                "Build a safe, rig-compatible 4x4 overlanding itinerary",
            )
        ),
    )

    log_history = list(state.get("intent_outcome_log", []))
    log_history.append(audit_entry.model_dump(mode="json"))
    state["intent_outcome_log"] = log_history[-20:]

    audit_logger.log_event(
        event_type="memory_bank_sync",
        message=f"Session memory sync completed (persisted={memory_persisted})",
        data={
            "session_id": str(session_id),
            "memory_persisted": memory_persisted,
            "tools_invoked": tools_called,
        },
        severity="INFO",
    )
    return None
