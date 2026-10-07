# ruff: noqa
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

"""Multi-model 4x4 Road Trip & Overlanding Planner Agent with Memory Bank, HITL, and Safety Plugins."""

import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App, ResumabilityConfig
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.plugins.context_filter_plugin import ContextFilterPlugin
from google.adk.plugins.reflect_retry_tool_plugin import (
    ReflectAndRetryToolPlugin,
)
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.app_utils.memory_config import (
    generate_memories_callback,
    initialize_overlanding_state,
)
from app.app_utils.safety_plugins import OffroadSafetyGuardrailPlugin
from app.tools import (
    calculate_offroad_fuel_plan,
    check_rig_trail_compatibility,
    get_trail_weather_and_elevation,
    requires_high_risk_confirmation,
    save_user_rig_profile,
    search_curated_trails,
    submit_backcountry_trip_registration,
)

load_dotenv()

# Multi-Model Tiering Strategy:
# 1. Coordinator Model (`gemini-3.8-flash`): Balanced tool orchestration & itinerary synthesis.
# 2. Fast Research & Compaction Model (`gemini-2.5-flash`): Low-latency web search & sliding-window event summarization.
# 3. Deep Safety Auditor Model (`gemini-2.5-pro`): High-reasoning multi-constraint backcountry risk & recovery auditing.
MODEL = "gemini-3.8-flash"
FAST_RESEARCH_MODEL = "gemini-2.5-flash"
SAFETY_AUDITOR_MODEL = "gemini-2.5-pro"


web_trail_researcher = Agent(
    name="web_trail_researcher",
    model=Gemini(
        model=FAST_RESEARCH_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Fast web research specialist (`gemini-2.5-flash`) that searches the web for "
        "4x4 trails outside the local catalog, current seasonal pass/gate closures, "
        "BLM/USFS permit rules, dispersed camping regulations, and nearby fuel stations."
    ),
    instruction=(
        "You are an off-road and overlanding trail research specialist. "
        "Use google_search to find accurate, up-to-date information on 4x4 trails, "
        "technical difficulty ratings (1-10), seasonal closures, permit requirements, "
        "dispersed/developed campgrounds, and fuel stops. Always summarize key facts "
        "concisely and note the managing agency (BLM, USFS, NPS) when applicable."
    ),
    tools=[google_search],
)


safety_compliance_auditor = Agent(
    name="safety_compliance_auditor",
    model=Gemini(
        model=SAFETY_AUDITOR_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Deep-reasoning backcountry safety & recovery compliance auditor (`gemini-2.5-pro`) "
        "invoked for complex multi-day remote traverses, extreme trails (rated >= 6/10), "
        "or compound weather/fuel/mechanical risk trade-offs."
    ),
    instruction=(
        "You are a senior 4x4 backcountry safety engineer and Tread Lightly! master trainer. "
        "Audit proposed off-road legs for mechanical failure points, recovery geometry, "
        "solo-travel stranding hazards, canyon flash-flood exposure, high-altitude hypoxia/freeze "
        "risks, and fuel reserve margins. Provide a concise, actionable safety audit with "
        "mandatory go/no-go criteria and emergency bailout coordinates/towns."
    ),
    tools=[
        check_rig_trail_compatibility,
        calculate_offroad_fuel_plan,
        get_trail_weather_and_elevation,
    ],
)


backcountry_registration_tool = FunctionTool(
    func=submit_backcountry_trip_registration,
    require_confirmation=requires_high_risk_confirmation,
)


SYSTEM_INSTRUCTION = """You are an expert 4x4 Road Trip & Overlanding Itinerary Planner.
Your mission is to build safe, realistic, day-by-day 4x4 road trip itineraries tailored to the user's vehicle build and backcountry safety rules.

### Active Session Context (Dynamically Injected from State & Memory)
- **Persisted User Rig Profile:** {user_rig_profile_summary}
- **Active Trip Region:** {active_trip_region}

### Mandatory Tool Workflow
Whenever a user asks to plan a trip, evaluate a trail, or check route logistics:
1. **Persist Vehicle Profile:** When the user shares or updates their 4x4 vehicle specifications, call `save_user_rig_profile` so their build is persisted across turns and sessions in `user:rig_profile` and saved as a JSON artifact.
2. **Discover Trails:** Call `search_curated_trails` for the target region/trail first. If the requested region or trail is not in the curated catalog (or the user asks for live permit/closure details), call `web_trail_researcher`.
3. **Validate Vehicle Compatibility:** For every candidate or requested trail, ALWAYS call `check_rig_trail_compatibility` using the user's vehicle specs (tire size in inches, ground clearance in inches, whether it has a true 4WD Low-range transfer case `has_4lo`, number of locking differentials `lockers`, `has_winch`, and `is_solo`).
   - If the user did not specify their vehicle specs and no profile is saved in state, assume a stock true 4WD with 4Lo (`tire_size_inches=31.0`, `clearance_inches=9.5`, `has_4lo=True`, `lockers=0`, `has_winch=False`, `is_solo=True`, `highway_mpg=18.0`, `tank_capacity_gallons=21.0`), state this assumption clearly, and invite them to share their exact build.
   - Note that AWD crossovers (e.g., Subaru Outback, RAV4, CR-V) do NOT have 4Lo (`has_4lo=False`) and are strictly capped at 2/10 graded dirt roads.
4. **Calculate Fuel & 25% Reserve:** For every daily leg or remote traverse, ALWAYS call `calculate_offroad_fuel_plan` to compute degraded off-road MPG, total gallons burned, % of tank used, and whether the leg stays within the 75% usable fuel budget (preserving the mandatory 25% reserve).
5. **Check Weather & Elevation:** Call `get_trail_weather_and_elevation` for the trip region to surface flash-flood risks (canyons/washes) and high-altitude freeze/snow advisories.
6. **Human-in-the-Loop Registration & Deep Safety Audit:** When a user asks to register/finalize a backcountry permit or dispatch on an extreme trail (`difficulty >= 7`), solo advanced route (`difficulty >= 6`), or permit-required traverse, call `submit_backcountry_trip_registration` (which triggers Human-in-the-Loop confirmation) and consult `safety_compliance_auditor` when deep multi-constraint risk analysis is needed.

### Strict Backcountry Safety Guardrails
- **Hard Capability Block:** NEVER schedule a trail in the primary itinerary if `check_rig_trail_compatibility` returns `is_compatible: False` (`REJECTED_UNSAFE_FOR_RIG`). Explicitly explain why the trail is unsafe for the rig (citing the exact missing equipment such as 4Lo, tire size, clearance, lockers, or winch) and substitute safe, compatible trails (`difficulty <= max_safe_difficulty`) in the same region.
- **25% Fuel Reserve Rule:** If `calculate_offroad_fuel_plan` shows `meets_25_percent_reserve_rule: False` (>75% tank utilization), prominently display a **FUEL RESERVE WARNING** stating the exact gallons needed, % of tank used, and the required auxiliary fuel (e.g., 5-gallon jerry cans / RotopaX) or mandatory fuel stop.
- **Solo & Recovery Advisories:** Always include any solo-travel or winch/recovery warnings returned by `check_rig_trail_compatibility` (especially on trails rated >= 6/10) and remind drivers to air down tires and carry a compressor/plug kit.
- **Responsible Trail Stewardship & Legal Access:** Recommend only legal, designated OHV/4x4 routes and authorized dispersed or developed campsites (noting required permits such as Canyonlands White Rim permits).

### Output Format for Itineraries
Present each itinerary clearly with:
- **Vehicle Profile & Max Safe Trail Rating (1-10)** (including any rejected trails and why)
- **Regional Weather, Elevation & Hazard Advisory**
- **Day-by-Day Plan** (for each day: Trail Name & Rating `X/10`, Rig Compatibility Verdict, Highway + Off-Road Mileage, Estimated Off-Road MPG & Fuel Burn `% of tank` + 25% Reserve Check, Nearest Fuel Stop, and Recommended Campsite)
- **Essential Recovery & Backcountry Checklist**
"""


root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="four_by_four_planner",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    before_agent_callback=initialize_overlanding_state,
    after_agent_callback=generate_memories_callback,
    tools=[
        PreloadMemoryTool(),
        search_curated_trails,
        check_rig_trail_compatibility,
        calculate_offroad_fuel_plan,
        get_trail_weather_and_elevation,
        save_user_rig_profile,
        backcountry_registration_tool,
        AgentTool(agent=web_trail_researcher),
        AgentTool(agent=safety_compliance_auditor),
    ],
)


def _build_plugins() -> list[BasePlugin]:
    """Assembles runner-wide safety, resilience, context-filtering, and analytics plugins."""
    plugins: list[BasePlugin] = [
        OffroadSafetyGuardrailPlugin(),
        ReflectAndRetryToolPlugin(
            max_retries=2,
            throw_exception_if_retry_exceeded=False,
        ),
        ContextFilterPlugin(num_invocations_to_keep=10),
    ]
    bq_dataset = os.environ.get("BQ_ANALYTICS_DATASET_ID")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if bq_dataset and project_id:
        try:
            from google.adk.plugins.bigquery_agent_analytics_plugin import (
                BigQueryAgentAnalyticsPlugin,
            )

            plugins.append(
                BigQueryAgentAnalyticsPlugin(
                    project_id=project_id,
                    dataset_id=bq_dataset,
                )
            )
        except Exception:
            pass
    return plugins


app = App(
    root_agent=root_agent,
    name="app",
    plugins=_build_plugins(),
    resumability_config=ResumabilityConfig(is_resumable=True),
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=4,
        overlap_size=1,
        summarizer=LlmEventSummarizer(
            llm=Gemini(
                model=FAST_RESEARCH_MODEL,
                retry_options=types.HttpRetryOptions(attempts=2),
            )
        ),
    ),
    context_cache_config=ContextCacheConfig(
        min_tokens=1024,
        ttl_seconds=1800,
        cache_intervals=5,
    ),
)
