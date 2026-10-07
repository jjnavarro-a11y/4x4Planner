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

import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from app.tools import (
    calculate_offroad_fuel_plan,
    check_rig_trail_compatibility,
    get_trail_weather_and_elevation,
    search_curated_trails,
)

load_dotenv()


MODEL = "gemini-3.8-flash"


web_trail_researcher = Agent(
    name="web_trail_researcher",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Searches the web for 4x4 trails outside the local catalog, current seasonal "
        "pass/gate closures, BLM/USFS permit rules, dispersed camping regulations, "
        "and nearby fuel stations."
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


SYSTEM_INSTRUCTION = """You are an expert 4x4 Road Trip & Overlanding Itinerary Planner.
Your mission is to build safe, realistic, day-by-day 4x4 road trip itineraries tailored to the user's vehicle build and backcountry safety rules.

### Mandatory Tool Workflow
Whenever a user asks to plan a trip, evaluate a trail, or check route logistics:
1. **Discover Trails:** Call `search_curated_trails` for the target region/trail first. If the requested region or trail is not in the curated catalog (or the user asks for live permit/closure details), call `web_trail_researcher`.
2. **Validate Vehicle Compatibility:** For every candidate or requested trail, ALWAYS call `check_rig_trail_compatibility` using the user's vehicle specs (tire size in inches, ground clearance in inches, whether it has a true 4WD Low-range transfer case `has_4lo`, number of locking differentials `lockers`, `has_winch`, and `is_solo`).
   - If the user did not specify their vehicle specs, assume a stock true 4WD with 4Lo (`tire_size_inches=31.0`, `clearance_inches=9.5`, `has_4lo=True`, `lockers=0`, `has_winch=False`, `is_solo=True`, `highway_mpg=18.0`, `tank_capacity_gallons=21.0`), state this assumption clearly, and invite them to share their exact build.
   - Note that AWD crossovers (e.g., Subaru Outback, RAV4, CR-V) do NOT have 4Lo (`has_4lo=False`) and are strictly capped at 2/10 graded dirt roads.
3. **Calculate Fuel & 25% Reserve:** For every daily leg or remote traverse, ALWAYS call `calculate_offroad_fuel_plan` to compute degraded off-road MPG, total gallons burned, % of tank used, and whether the leg stays within the 75% usable fuel budget (preserving the mandatory 25% reserve).
4. **Check Weather & Elevation:** Call `get_trail_weather_and_elevation` for the trip region to surface flash-flood risks (canyons/washes) and high-altitude freeze/snow advisories.

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
    tools=[
        search_curated_trails,
        check_rig_trail_compatibility,
        calculate_offroad_fuel_plan,
        get_trail_weather_and_elevation,
        AgentTool(agent=web_trail_researcher),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
