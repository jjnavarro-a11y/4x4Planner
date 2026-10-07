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
"""Unit tests for deterministic 4x4 trip planning tools, schemas, memory, safety plugins, and telemetry."""

import json
import logging

import pytest

from app.agent import (
    FAST_RESEARCH_MODEL,
    MODEL,
    SAFETY_AUDITOR_MODEL,
    app,
    root_agent,
    safety_compliance_auditor,
    web_trail_researcher,
)
from app.app_utils.memory_config import memory_bank_config
from app.app_utils.safety_plugins import OffroadSafetyGuardrailPlugin
from app.app_utils.secrets import get_secret, mask_secret
from app.app_utils.telemetry import (
    PiiRedactor,
    StructuredJsonFormatter,
    intent_outcome_tracker,
)
from app.app_utils.typing import (
    BackcountryPermitApprovalOutput,
    FuelPlanOutput,
    RigCompatibilityOutput,
    SavedRigProfileOutput,
    TrailSearchOutput,
    TrailWeatherOutput,
)
from app.tools import (
    calculate_offroad_fuel_plan,
    check_rig_trail_compatibility,
    get_trail_weather_and_elevation,
    requires_high_risk_confirmation,
    save_user_rig_profile,
    search_curated_trails,
    submit_backcountry_trip_registration,
)


def test_agent_and_app_definitions() -> None:
    """Verifies that root_agent, multi-model specialists, and app are properly configured."""
    assert root_agent.name == "four_by_four_planner"
    assert app.name == "app"
    assert len(root_agent.tools) >= 7
    assert root_agent.model.model == MODEL
    assert web_trail_researcher.model.model == FAST_RESEARCH_MODEL
    assert safety_compliance_auditor.model.model == SAFETY_AUDITOR_MODEL
    assert app.resumability_config is not None
    assert app.resumability_config.is_resumable is True
    assert app.events_compaction_config is not None
    assert app.context_cache_config is not None
    assert any(isinstance(p, OffroadSafetyGuardrailPlugin) for p in app.plugins)


def test_search_curated_trails() -> None:
    """Verifies curated trail catalog filtering and strict TrailSearchOutput schema."""
    result = search_curated_trails(region="Moab", max_difficulty=4)
    assert isinstance(result, TrailSearchOutput)
    assert result["status"] == "success"
    assert result["matching_trails_count"] >= 4
    assert all(t["difficulty"] <= 4 for t in result["matching_trails"])
    assert all(t["difficulty"] > 4 for t in result["harder_trails_in_region"])


def test_rig_compatibility_blocks_awd_on_technical_trail() -> None:
    """Verifies that an AWD crossover without 4Lo is blocked on a 8/10 rock-crawling trail."""
    res = check_rig_trail_compatibility(
        trail_name="Rubicon Trail",
        trail_difficulty=8,
        tire_size_inches=29.0,
        clearance_inches=8.7,
        has_4lo=False,
        lockers=0,
        has_winch=False,
        is_solo=True,
    )
    assert isinstance(res, RigCompatibilityOutput)
    assert res["is_compatible"] is False
    assert res["max_safe_difficulty"] == 2
    assert res["verdict"] == "REJECTED_UNSAFE_FOR_RIG"
    assert len(res["blocking_reasons"]) > 0
    assert res.recovery_instructions is not None


def test_rig_compatibility_approves_stock_4x4_on_moderate_trail() -> None:
    """Verifies that a stock 4x4 with 4Lo is approved for a 4/10 trail."""
    res = check_rig_trail_compatibility(
        trail_name="Fins and Things",
        trail_difficulty=4,
        tire_size_inches=31.0,
        clearance_inches=9.6,
        has_4lo=True,
        lockers=1,
        has_winch=False,
        is_solo=True,
    )
    assert isinstance(res, RigCompatibilityOutput)
    assert res["is_compatible"] is True
    assert res["max_safe_difficulty"] >= 4
    assert res["verdict"] == "APPROVED"


def test_fuel_plan_enforces_25_percent_reserve_rule() -> None:
    """Verifies fuel consumption math and 25% reserve rule enforcement."""
    short_leg = calculate_offroad_fuel_plan(
        highway_miles=20.0,
        offroad_miles=15.0,
        trail_difficulty=3,
        highway_mpg=18.0,
        tank_capacity_gallons=23.0,
    )
    assert isinstance(short_leg, FuelPlanOutput)
    assert short_leg["meets_25_percent_reserve_rule"] is True
    assert short_leg["auxiliary_fuel_required_gallons"] == 0.0

    long_leg = calculate_offroad_fuel_plan(
        highway_miles=35.0,
        offroad_miles=100.0,
        trail_difficulty=4,
        highway_mpg=15.0,
        tank_capacity_gallons=17.5,
    )
    assert isinstance(long_leg, FuelPlanOutput)
    assert long_leg["meets_25_percent_reserve_rule"] is False
    assert long_leg["auxiliary_fuel_required_gallons"] > 0.0
    assert long_leg["recommended_5gal_jerry_cans"] >= 1
    assert long_leg.recovery_instructions is not None


def test_weather_and_elevation_returns_valid_structure() -> None:
    """Verifies weather and elevation tool contract."""
    weather = get_trail_weather_and_elevation(location_name="Moab, Utah")
    assert isinstance(weather, TrailWeatherOutput)
    assert weather["status"] == "success"
    assert "elevation_feet" in weather
    assert "flash_flood_risk" in weather
    assert "alpine_snow_ice_risk" in weather


@pytest.mark.asyncio
async def test_save_user_rig_profile_and_hitl_registration() -> None:
    """Verifies rig profile tool and Human-in-the-Loop confirmation predicate."""
    saved = await save_user_rig_profile(
        vehicle_name="2023 Toyota 4Runner TRD Pro",
        tire_size_inches=33.0,
        clearance_inches=10.5,
        has_4lo=True,
        lockers=1,
        has_winch=False,
        highway_mpg=17.0,
        tank_capacity_gallons=23.0,
        is_solo=True,
    )
    assert isinstance(saved, SavedRigProfileOutput)
    assert saved.profile.max_safe_difficulty == 6

    assert requires_high_risk_confirmation("Pritchett Canyon", 9, False, False) is True
    assert requires_high_risk_confirmation("Hell's Revenge", 6, True, False) is True
    assert requires_high_risk_confirmation("White Rim Road", 4, False, True) is True
    assert requires_high_risk_confirmation("Gemini Bridges", 3, False, False) is False

    reg = submit_backcountry_trip_registration(
        trail_name="Gemini Bridges",
        region="Moab, Utah",
        trail_difficulty=3,
        is_solo=False,
        requires_nps_permit=False,
    )
    assert isinstance(reg, BackcountryPermitApprovalOutput)
    assert reg.status == "approved"


def test_pii_redaction_and_intent_outcome_telemetry() -> None:
    """Verifies PII redaction, structured JSON formatting, and Intent vs. Outcome tracking."""
    raw = (
        "Driver email is trail.driver@example.com, phone 415-555-0199, SSN 123-45-6789."
    )
    scrubbed, count = PiiRedactor.redact_text(raw)
    assert count == 3
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_SSN]" in scrubbed

    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="User email test@example.com logged",
        args=(),
        exc_info=None,
    )
    formatted_json = json.loads(formatter.format(record))
    assert formatted_json["service_name"] == "four-by-four-planner"
    assert "[REDACTED_EMAIL]" in formatted_json["message"]

    intent_outcome_tracker.record_intent(
        invocation_id="inv-test-1",
        session_id="sess-test-1",
        actor="check_rig_trail_compatibility",
        stage="tool",
        declared_intent="Validate rig compatibility on Rubicon Trail",
        raw_inputs={"email": "driver@example.com", "trail_difficulty": 8},
    )
    entry = intent_outcome_tracker.record_outcome(
        invocation_id="inv-test-1",
        session_id="sess-test-1",
        actor="check_rig_trail_compatibility",
        stage="tool",
        status="blocked_by_guardrail",
        intent_fulfilled=False,
        actual_outcome_summary="Rejected AWD vehicle on 8/10 trail",
        safety_verdict="REJECTED_UNSAFE_FOR_RIG",
        discrepancy_reason="Missing 4Lo, lockers, and 35-inch tires",
    )
    assert entry.intent.actor == "check_rig_trail_compatibility"
    assert entry.outcome.status == "blocked_by_guardrail"
    assert entry.outcome.intent_fulfilled is False


def test_memory_bank_and_secret_manager_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies Memory Bank config topics and Secret Manager fallback helper."""
    assert memory_bank_config is not None
    assert len(memory_bank_config.customization_configs) == 1
    assert len(memory_bank_config.customization_configs[0].memory_topics) >= 5

    monkeypatch.setenv("TEST_OFFROAD_SECRET", "my-secret-token-99")
    val = get_secret("TEST_OFFROAD_SECRET")
    assert val == "my-secret-token-99"
    assert mask_secret(val) == "my***99"
