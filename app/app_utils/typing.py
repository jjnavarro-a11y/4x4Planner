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

"""Strict Pydantic schemas for tool inputs, tool outputs, telemetry, and feedback."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictToolModel(BaseModel):
    """Base Pydantic model with strict schema enforcement and mapping compatibility.

    Enforces `extra="forbid"` so all fields are strictly validated while providing
    read-only mapping methods (`__getitem__`, `get`, `__contains__`, `keys`, `items`)
    so callers and ADK serializers can access fields via attribute or key syntax.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def __getitem__(self, key: str) -> Any:
        data = self.model_dump(mode="python")
        return data[key]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self.__class__.model_fields

    def get(self, key: str, default: Any = None) -> Any:
        data = self.model_dump(mode="python")
        return data.get(key, default)

    def keys(self) -> Any:
        return self.model_dump(mode="python").keys()

    def items(self) -> Any:
        return self.model_dump(mode="python").items()

    def values(self) -> Any:
        return self.model_dump(mode="python").values()


class TrailRecord(StrictToolModel):
    """Strict schema for a curated 4x4 trail entry."""

    name: str = Field(..., description="Official name of the 4x4 trail.")
    region: str = Field(..., description="Geographic region and state of the trail.")
    difficulty: int = Field(
        ..., ge=1, le=10, description="Technical 4x4 trail rating on a 1-10 scale."
    )
    distance_miles: float = Field(
        ..., gt=0.0, description="Off-road trail distance in miles."
    )
    highway_approach_miles: float = Field(
        ..., ge=0.0, description="Paved highway miles to/from nearest fuel town."
    )
    estimated_hours: float = Field(
        ..., gt=0.0, description="Estimated driving duration in hours."
    )
    min_tire_inches: float = Field(
        ...,
        ge=25.0,
        le=44.0,
        description="Minimum recommended tire diameter in inches.",
    )
    min_clearance_inches: float = Field(
        ..., ge=6.0, le=20.0, description="Minimum ground clearance in inches."
    )
    requires_4lo: bool = Field(
        ...,
        description="Whether a true two-speed 4WD Low-range transfer case is required.",
    )
    min_lockers: int = Field(
        ...,
        ge=0,
        le=2,
        description="Minimum number of locking differentials required (0, 1, or 2).",
    )
    requires_winch: bool = Field(
        ..., description="Whether a front recovery winch is mandatory."
    )
    nearest_fuel: str = Field(
        ..., description="Nearest reliable town or gas station for refueling."
    )
    camping: str = Field(
        ...,
        description="Designated BLM/USFS/NPS dispersed or developed camping options.",
    )
    flash_flood_sensitive: bool = Field(
        ..., description="True if route traverses slot canyons, washes, or creek beds."
    )
    summary: str = Field(
        ..., description="Concise summary of terrain, obstacles, and scenery."
    )


class RegionalWeatherBaseline(StrictToolModel):
    """Strict schema for offline fallback regional weather baseline."""

    resolved_location: str = Field(..., description="Canonical location display name.")
    elevation_feet: int = Field(
        ..., ge=-500, le=15000, description="Elevation in feet."
    )
    high_temp_f: float = Field(..., description="3-day high temperature in Fahrenheit.")
    low_temp_f: float = Field(..., description="3-day low temperature in Fahrenheit.")
    precip_probability_percent: int = Field(
        ..., ge=0, le=100, description="Maximum precipitation probability percentage."
    )
    max_wind_mph: float = Field(..., ge=0.0, description="Maximum wind speed in MPH.")
    flash_flood_risk: str = Field(
        ..., description="Flash flood hazard level and guidance."
    )
    alpine_snow_ice_risk: str = Field(
        ..., description="High-altitude freeze/snow/ice hazard level and guidance."
    )


class TrailSearchOutput(StrictToolModel):
    """Strict output schema for `search_curated_trails`."""

    status: Literal["success", "error"] = Field(
        default="success", description="Execution status of the trail search."
    )
    queried_region: str = Field(..., description="Region or trail query string.")
    max_difficulty_filter: int = Field(
        ..., ge=1, le=10, description="Maximum trail difficulty filter applied (1-10)."
    )
    matching_trails_count: int = Field(
        ..., ge=0, description="Count of trails matching the region and difficulty cap."
    )
    matching_trails: list[TrailRecord] = Field(
        default_factory=list,
        description="Trails in the region rated at or below max_difficulty.",
    )
    harder_trails_in_region: list[TrailRecord] = Field(
        default_factory=list,
        description="Trails in the region exceeding max_difficulty (for comparison/rejection).",
    )
    recovery_instructions: str | None = Field(
        default=None,
        description="Explicit LLM recovery guidance if no exact region matched or input was invalid.",
    )


class RigCompatibilityOutput(StrictToolModel):
    """Strict output schema for `check_rig_trail_compatibility`."""

    status: Literal["success", "error"] = Field(
        default="success", description="Execution status of the compatibility check."
    )
    trail_name: str = Field(..., description="Name of the evaluated 4x4 trail.")
    trail_difficulty: int = Field(
        ..., ge=1, le=10, description="Technical difficulty rating of the trail (1-10)."
    )
    max_safe_difficulty: int = Field(
        ...,
        ge=1,
        le=10,
        description="Maximum trail rating (1-10) the user's vehicle can safely tackle.",
    )
    is_compatible: bool = Field(
        ..., description="True if trail_difficulty <= max_safe_difficulty."
    )
    verdict: Literal["APPROVED", "REJECTED_UNSAFE_FOR_RIG"] = Field(
        ..., description="Deterministic pass/fail safety verdict."
    )
    blocking_reasons: list[str] = Field(
        default_factory=list,
        description="Specific mechanical/equipment deficiencies blocking approval.",
    )
    safety_warnings: list[str] = Field(
        default_factory=list,
        description="Mandatory backcountry recovery, solo-travel, and tire-pressure warnings.",
    )
    recovery_instructions: str | None = Field(
        default=None,
        description="Explicit LLM recovery instructions when a trail is rejected.",
    )


class FuelPlanOutput(StrictToolModel):
    """Strict output schema for `calculate_offroad_fuel_plan`."""

    status: Literal["success", "error"] = Field(
        default="success", description="Execution status of the fuel calculation."
    )
    highway_miles: float = Field(
        ..., ge=0.0, description="Paved highway miles for the leg."
    )
    offroad_miles: float = Field(
        ..., ge=0.0, description="Off-road trail miles for the leg."
    )
    total_leg_miles: float = Field(
        ..., ge=0.0, description="Combined highway and off-road miles."
    )
    highway_mpg: float = Field(
        ..., gt=0.0, description="Rated highway fuel economy in MPG."
    )
    estimated_offroad_mpg: float = Field(
        ...,
        gt=0.0,
        description="Degraded off-road MPG after low-range terrain penalty.",
    )
    total_fuel_needed_gallons: float = Field(
        ..., ge=0.0, description="Total estimated fuel burned in US gallons."
    )
    tank_capacity_gallons: float = Field(
        ..., gt=0.0, description="Total vehicle fuel tank capacity in US gallons."
    )
    usable_75_percent_budget_gallons: float = Field(
        ...,
        gt=0.0,
        description="Maximum usable fuel (75% of tank) preserving 25% reserve.",
    )
    mandatory_25_percent_reserve_gallons: float = Field(
        ..., gt=0.0, description="Mandatory 25% backcountry fuel reserve in gallons."
    )
    tank_utilization_percent: float = Field(
        ..., ge=0.0, description="Percentage of total fuel tank consumed by the leg."
    )
    meets_25_percent_reserve_rule: bool = Field(
        ..., description="True if total fuel needed is within the 75% usable budget."
    )
    auxiliary_fuel_required_gallons: float = Field(
        ..., ge=0.0, description="Extra fuel in gallons required beyond the 75% budget."
    )
    recommended_5gal_jerry_cans: int = Field(
        ..., ge=0, description="Number of 5-gallon jerry cans / RotopaX required."
    )
    fuel_safety_status: Literal[
        "SAFE_WITHIN_75_PERCENT_BUDGET",
        "WARNING_EXCEEDS_75_PERCENT_BUDGET_AUX_FUEL_REQUIRED",
    ] = Field(..., description="Fuel reserve compliance status code.")
    advisory: str = Field(
        ..., description="Human-readable fuel consumption and reserve advisory."
    )
    recovery_instructions: str | None = Field(
        default=None,
        description="LLM recovery instructions when the leg exceeds the 75% fuel budget.",
    )


class TrailWeatherOutput(StrictToolModel):
    """Strict output schema for `get_trail_weather_and_elevation`."""

    status: Literal["success", "error"] = Field(
        default="success", description="Execution status of the weather lookup."
    )
    source: Literal["live_open_meteo", "regional_backcountry_baseline"] = Field(
        ...,
        description="Whether forecast came from live Open-Meteo or regional baseline.",
    )
    queried_location: str = Field(..., description="Location string requested.")
    resolved_location: str = Field(
        ..., description="Geocoded or canonical location name."
    )
    elevation_feet: int = Field(
        ..., ge=-500, le=15000, description="Trailhead or regional elevation in feet."
    )
    three_day_high_temp_f: float = Field(
        ..., description="Maximum 3-day high temperature in Fahrenheit."
    )
    three_day_low_temp_f: float = Field(
        ..., description="Minimum 3-day overnight low temperature in Fahrenheit."
    )
    max_precip_probability_percent: int = Field(
        ...,
        ge=0,
        le=100,
        description="Peak 3-day precipitation probability percentage.",
    )
    max_wind_mph: float = Field(
        ..., ge=0.0, description="Peak 3-day wind speed in MPH."
    )
    flash_flood_risk: str = Field(
        ..., description="Canyon/wash flash-flood risk assessment."
    )
    alpine_snow_ice_risk: str = Field(
        ..., description="High-elevation snow/ice risk assessment."
    )
    note: str = Field(
        default="Verify live local NOAA / USFS / BLM ranger station conditions prior to trailhead departure.",
        description="Backcountry verification guidance.",
    )
    recovery_instructions: str | None = Field(
        default=None,
        description="Explicit LLM recovery instructions if fallback baseline was used.",
    )


class UserRigProfile(StrictToolModel):
    """Strict schema for a user's persisted 4x4 vehicle profile in session/user state."""

    vehicle_name: str = Field(
        default="Stock 4WD (Assumed)",
        description="Make/model/trim of the user's 4x4 rig.",
    )
    tire_size_inches: float = Field(
        default=31.0, ge=25.0, le=44.0, description="Tire diameter in inches."
    )
    clearance_inches: float = Field(
        default=9.5, ge=5.0, le=20.0, description="Minimum ground clearance in inches."
    )
    has_4lo: bool = Field(
        default=True, description="True if equipped with a 4WD Low-range transfer case."
    )
    lockers: int = Field(
        default=0,
        ge=0,
        le=2,
        description="Number of locking differentials (0, 1, or 2).",
    )
    has_winch: bool = Field(
        default=False, description="True if equipped with a front recovery winch."
    )
    highway_mpg: float = Field(
        default=18.0, gt=1.0, le=60.0, description="Highway fuel economy in MPG."
    )
    tank_capacity_gallons: float = Field(
        default=21.0, gt=1.0, le=60.0, description="Fuel tank capacity in US gallons."
    )
    is_solo: bool = Field(
        default=True,
        description="True if traveling solo without a recovery buddy vehicle.",
    )
    max_safe_difficulty: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Computed maximum safe trail difficulty (1-10).",
    )


class SavedRigProfileOutput(StrictToolModel):
    """Strict output schema for `save_user_rig_profile`."""

    status: Literal["success", "error"] = Field(
        default="success", description="Status of saving the rig profile."
    )
    profile: UserRigProfile = Field(
        ..., description="Validated 4x4 vehicle profile persisted to user state."
    )
    persisted_to_state_key: str = Field(
        default="user:rig_profile",
        description="Session state key where the profile was stored.",
    )
    artifact_saved: bool = Field(
        default=False,
        description="Whether a JSON artifact snapshot of the rig profile was saved.",
    )
    summary: str = Field(
        ..., description="Human-readable summary of the saved rig capabilities."
    )


class BackcountryPermitApprovalOutput(StrictToolModel):
    """Strict output schema for Human-in-the-Loop `submit_backcountry_trip_registration`."""

    status: Literal["approved", "pending_human_confirmation", "rejected"] = Field(
        ..., description="Approval status of the backcountry trip registration."
    )
    registration_id: str = Field(
        default_factory=lambda: f"reg-{uuid.uuid4().hex[:8]}",
        description="Unique backcountry registration identifier.",
    )
    region: str = Field(..., description="Target backcountry region.")
    trail_name: str = Field(..., description="Primary 4x4 trail being registered.")
    trail_difficulty: int = Field(
        ..., ge=1, le=10, description="Technical difficulty rating of the trail (1-10)."
    )
    is_solo: bool = Field(..., description="Whether the expedition is solo.")
    requires_human_confirmation: bool = Field(
        ...,
        description="True if high-risk criteria triggered a Human-in-the-Loop confirmation gate.",
    )
    human_confirmed: bool = Field(
        ...,
        description="True if a human operator confirmed the high-risk registration.",
    )
    advisory: str = Field(
        ..., description="Detailed permit, safety, and emergency check-in advisory."
    )
    recovery_instructions: str | None = Field(
        default=None,
        description="Instructions for the agent if human confirmation is pending or rejected.",
    )


class IntentRecord(StrictToolModel):
    """Structured capture of an agent, model, or tool invocation's intent."""

    invocation_id: str = Field(..., description="Unique invocation or correlation ID.")
    session_id: str = Field(default="unknown", description="Active session ID.")
    actor: str = Field(..., description="Agent or tool name initiating the action.")
    stage: Literal["agent", "model", "tool", "user_prompt"] = Field(
        ..., description="Lifecycle stage of the intent."
    )
    declared_intent: str = Field(
        ..., description="Semantic description of what the step intends to achieve."
    )
    sanitized_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="PII-redacted input parameters or prompt summary.",
    )
    timestamp_start_ms: float = Field(
        ..., description="Epoch timestamp in milliseconds when intent was recorded."
    )


class OutcomeRecord(StrictToolModel):
    """Structured capture of the actual outcome paired with a prior IntentRecord."""

    invocation_id: str = Field(..., description="Matching invocation ID.")
    actor: str = Field(..., description="Agent or tool name completing the action.")
    stage: Literal["agent", "model", "tool", "user_prompt"] = Field(
        ..., description="Lifecycle stage of the outcome."
    )
    status: Literal["success", "blocked_by_guardrail", "error", "pending_hitl"] = Field(
        ..., description="Execution outcome status."
    )
    intent_fulfilled: bool = Field(
        ..., description="Whether the actual outcome satisfied the declared intent."
    )
    safety_verdict: str = Field(
        default="PASS", description="Safety and guardrail compliance verdict."
    )
    actual_outcome_summary: str = Field(
        ..., description="PII-redacted summary of the actual output or decision."
    )
    discrepancy_reason: str | None = Field(
        default=None,
        description="Explanation if actual outcome diverged from declared intent.",
    )
    latency_ms: float = Field(
        default=0.0, ge=0.0, description="Execution duration in milliseconds."
    )


class IntentOutcomeAuditEntry(StrictToolModel):
    """Combined Intent vs. Outcome structured audit log record."""

    event_type: Literal["intent_vs_outcome"] = "intent_vs_outcome"
    service_name: str = "four-by-four-planner"
    intent: IntentRecord
    outcome: OutcomeRecord
    pii_redacted_count: int = Field(
        default=0, ge=0, description="Number of PII tokens redacted during this step."
    )


class Feedback(BaseModel):
    """Represents end-user feedback for a conversation."""

    model_config = ConfigDict(extra="forbid")

    score: int | float = Field(
        ..., ge=0, le=5, description="Numeric feedback score between 0 and 5."
    )
    text: str | None = Field(
        default="",
        description="Optional free-text user feedback (PII-redacted before logging).",
    )
    log_type: Literal["feedback"] = "feedback"
    service_name: Literal["four-by-four-planner"] = "four-by-four-planner"
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
