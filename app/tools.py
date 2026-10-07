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

"""Deterministic tools for the 4x4 Road Trip Planner Agent."""

import json
import math
import urllib.parse
import urllib.request
from typing import Any

CURATED_TRAILS: list[dict[str, Any]] = [
    # Moab, Utah
    {
        "name": "Shafer Trail & Potash Road",
        "region": "Moab, Utah",
        "difficulty": 2,
        "distance_miles": 19.0,
        "highway_approach_miles": 12.0,
        "estimated_hours": 2.5,
        "min_tire_inches": 29.0,
        "min_clearance_inches": 8.0,
        "requires_4lo": False,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Shafer Basin BLM dispersed sites or Horsethief Campground (BLM)",
        "flash_flood_sensitive": True,
        "summary": "Iconic graded switchbacks descending 1,500 ft from Island in the Sky along the Colorado River.",
    },
    {
        "name": "Gemini Bridges",
        "region": "Moab, Utah",
        "difficulty": 3,
        "distance_miles": 14.0,
        "highway_approach_miles": 10.0,
        "estimated_hours": 2.5,
        "min_tire_inches": 30.0,
        "min_clearance_inches": 8.8,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Horsethief Campground (BLM) or Bride Canyon dispersed campsites",
        "flash_flood_sensitive": True,
        "summary": "Scenic moderate 4x4 trail with minor rock steps leading to twin natural sandstone bridges.",
    },
    {
        "name": "Onion Creek & Fisher Towers",
        "region": "Moab, Utah",
        "difficulty": 3,
        "distance_miles": 20.0,
        "highway_approach_miles": 22.0,
        "estimated_hours": 3.0,
        "min_tire_inches": 30.0,
        "min_clearance_inches": 9.0,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Onion Creek BLM designated dispersed campsites",
        "flash_flood_sensitive": True,
        "summary": "Features 26 shallow creek crossings through narrow red-rock canyon walls; avoid during rain.",
    },
    {
        "name": "Fins and Things",
        "region": "Moab, Utah",
        "difficulty": 4,
        "distance_miles": 10.0,
        "highway_approach_miles": 5.0,
        "estimated_hours": 3.5,
        "min_tire_inches": 31.0,
        "min_clearance_inches": 9.5,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Sand Flats Recreation Area Campgrounds (Loops A-J)",
        "flash_flood_sensitive": False,
        "summary": "Classic slickrock rollercoaster with steep climbs and descents; ideal for stock high-clearance 4x4s with 4Lo.",
    },
    {
        "name": "White Rim Road",
        "region": "Moab, Utah",
        "difficulty": 4,
        "distance_miles": 100.0,
        "highway_approach_miles": 35.0,
        "estimated_hours": 14.0,
        "min_tire_inches": 31.0,
        "min_clearance_inches": 9.5,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT (no fuel along the entire 100-mile trail)",
        "camping": "Canyonlands NPS permit-required campsites (Murphy Hogback, White Crack, Potato Bottom)",
        "flash_flood_sensitive": True,
        "summary": "Remote 100-mile multi-day backcountry loop around Island in the Sky; requires NPS permit and auxiliary fuel planning.",
    },
    {
        "name": "Hell's Revenge",
        "region": "Moab, Utah",
        "difficulty": 6,
        "distance_miles": 6.5,
        "highway_approach_miles": 5.0,
        "estimated_hours": 3.5,
        "min_tire_inches": 33.0,
        "min_clearance_inches": 10.5,
        "requires_4lo": True,
        "min_lockers": 1,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Sand Flats Recreation Area Campgrounds",
        "flash_flood_sensitive": False,
        "summary": "Steep slickrock domes, narrow knife-edge ridges, and optional extreme obstacles (Hell's Gate).",
    },
    {
        "name": "Poison Spider Mesa",
        "region": "Moab, Utah",
        "difficulty": 6,
        "distance_miles": 14.0,
        "highway_approach_miles": 12.0,
        "estimated_hours": 4.5,
        "min_tire_inches": 33.0,
        "min_clearance_inches": 10.5,
        "requires_4lo": True,
        "min_lockers": 1,
        "requires_winch": False,
        "nearest_fuel": "Moab, UT",
        "camping": "Williams Bottom BLM Campground along UT-279",
        "flash_flood_sensitive": False,
        "summary": "Technical sandstone ledges, waterfalls, and sand sections with panoramic views of Moab Valley.",
    },
    {
        "name": "Pritchett Canyon",
        "region": "Moab, Utah",
        "difficulty": 9,
        "distance_miles": 8.0,
        "highway_approach_miles": 6.0,
        "estimated_hours": 6.5,
        "min_tire_inches": 37.0,
        "min_clearance_inches": 12.5,
        "requires_4lo": True,
        "min_lockers": 2,
        "requires_winch": True,
        "nearest_fuel": "Moab, UT",
        "camping": "Kane Creek Boulevard BLM campgrounds",
        "flash_flood_sensitive": True,
        "summary": "Moab's hardest natural rock-crawling trail (Chewy Hill, Rocker Knocker, Rock Pile); requires 37s, dual lockers, and winch.",
    },
    # Sierra Nevada / Lake Tahoe / Rubicon, California
    {
        "name": "Barker Pass to Blackwood Canyon Scenic Dirt Road",
        "region": "Sierra Nevada / Lake Tahoe, California",
        "difficulty": 2,
        "distance_miles": 14.0,
        "highway_approach_miles": 8.0,
        "estimated_hours": 2.0,
        "min_tire_inches": 28.5,
        "min_clearance_inches": 8.0,
        "requires_4lo": False,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Tahoe City, CA",
        "camping": "Kaspian Campground or Barker Pass USFS dispersed sites",
        "flash_flood_sensitive": False,
        "summary": "Scenic graded Sierra forest road with Lake Tahoe views; safe for AWD crossovers and stock SUVs.",
    },
    {
        "name": "Leek Springs & Mormon Emigrant Ridge",
        "region": "Sierra Nevada / Lake Tahoe, California",
        "difficulty": 2,
        "distance_miles": 22.0,
        "highway_approach_miles": 15.0,
        "estimated_hours": 2.5,
        "min_tire_inches": 28.5,
        "min_clearance_inches": 8.0,
        "requires_4lo": False,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Pollock Pines or Kirkwood, CA",
        "camping": "Silver Fork USFS Campground or Leek Springs dispersed sites",
        "flash_flood_sensitive": False,
        "summary": "Easy high-country gravel/dirt ridge road near the Eldorado National Forest; AWD compatible.",
    },
    {
        "name": "Ellis Peak Trail",
        "region": "Sierra Nevada / Lake Tahoe, California",
        "difficulty": 4,
        "distance_miles": 6.0,
        "highway_approach_miles": 12.0,
        "estimated_hours": 2.5,
        "min_tire_inches": 31.0,
        "min_clearance_inches": 9.5,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Tahoe City, CA",
        "camping": "Ellis Peak summit dispersed camping",
        "flash_flood_sensitive": False,
        "summary": "Granite steps and forest climbs near Barker Pass suitable for stock 4WD vehicles with 4Lo.",
    },
    {
        "name": "Rubicon Trail",
        "region": "Sierra Nevada / Lake Tahoe, California",
        "difficulty": 8,
        "distance_miles": 22.0,
        "highway_approach_miles": 25.0,
        "estimated_hours": 14.0,
        "min_tire_inches": 35.0,
        "min_clearance_inches": 11.5,
        "requires_4lo": True,
        "min_lockers": 2,
        "requires_winch": True,
        "nearest_fuel": "Georgetown or Tahoma, CA",
        "camping": "Buck Island Lake or Rubicon Springs campsites",
        "flash_flood_sensitive": False,
        "summary": "Legendary granite boulder-crawling trail (Gatekeeper, Soup Bowl, Big Sluice, Cadillac Hill); requires heavily built 4x4.",
    },
    # San Juan Mountains / Alpine Loop, Colorado
    {
        "name": "Cinnamon Pass & Animas Forks",
        "region": "San Juan Mountains, Colorado",
        "difficulty": 3,
        "distance_miles": 28.0,
        "highway_approach_miles": 10.0,
        "estimated_hours": 3.5,
        "min_tire_inches": 30.0,
        "min_clearance_inches": 8.8,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Silverton or Lake City, CO",
        "camping": "Mill Creek Campground (BLM) or Animas Forks dispersed areas",
        "flash_flood_sensitive": False,
        "summary": "12,640-ft alpine pass connecting Silverton and Lake City past historic ghost towns.",
    },
    {
        "name": "Ophir Pass",
        "region": "San Juan Mountains, Colorado",
        "difficulty": 3,
        "distance_miles": 10.0,
        "highway_approach_miles": 8.0,
        "estimated_hours": 2.0,
        "min_tire_inches": 30.0,
        "min_clearance_inches": 9.0,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Silverton or Telluride, CO",
        "camping": "Alta Lakes USFS dispersed camping",
        "flash_flood_sensitive": False,
        "summary": "11,789-ft rocky shelf road over the San Juan Mountains; requires 4Lo for steep engine braking.",
    },
    {
        "name": "Imogene Pass",
        "region": "San Juan Mountains, Colorado",
        "difficulty": 5,
        "distance_miles": 17.0,
        "highway_approach_miles": 5.0,
        "estimated_hours": 4.0,
        "min_tire_inches": 32.0,
        "min_clearance_inches": 10.0,
        "requires_4lo": True,
        "min_lockers": 1,
        "requires_winch": False,
        "nearest_fuel": "Ouray or Telluride, CO",
        "camping": "Angel Creek USFS Campground",
        "flash_flood_sensitive": False,
        "summary": "13,114-ft high alpine pass with rock ledges, stream crossings, and steep shelf exposures.",
    },
    {
        "name": "Black Bear Pass",
        "region": "San Juan Mountains, Colorado",
        "difficulty": 7,
        "distance_miles": 12.0,
        "highway_approach_miles": 10.0,
        "estimated_hours": 4.0,
        "min_tire_inches": 35.0,
        "min_clearance_inches": 11.0,
        "requires_4lo": True,
        "min_lockers": 2,
        "requires_winch": False,
        "nearest_fuel": "Silverton or Telluride, CO",
        "camping": "Alta Lakes USFS dispersed camping",
        "flash_flood_sensitive": False,
        "summary": "Infamous one-way descent down The Steps and tight off-camber switchbacks above Telluride.",
    },
    # Death Valley, California
    {
        "name": "Titus Canyon",
        "region": "Death Valley, California",
        "difficulty": 2,
        "distance_miles": 27.0,
        "highway_approach_miles": 15.0,
        "estimated_hours": 3.0,
        "min_tire_inches": 29.0,
        "min_clearance_inches": 8.0,
        "requires_4lo": False,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Beatty, NV or Furnace Creek, CA",
        "camping": "Texas Springs or Sunset NPS Campground",
        "flash_flood_sensitive": True,
        "summary": "One-way scenic desert mountain pass and narrow slot canyon exit.",
    },
    {
        "name": "Mengel Pass & Butte Valley",
        "region": "Death Valley, California",
        "difficulty": 5,
        "distance_miles": 45.0,
        "highway_approach_miles": 35.0,
        "estimated_hours": 6.0,
        "min_tire_inches": 33.0,
        "min_clearance_inches": 10.0,
        "requires_4lo": True,
        "min_lockers": 1,
        "requires_winch": False,
        "nearest_fuel": "Panamint Springs, CA",
        "camping": "Warm Spring Canyon primitive dispersed sites",
        "flash_flood_sensitive": True,
        "summary": "Remote desert backcountry traverse through Goler Wash and rocky Mengel Pass.",
    },
    # Sedona, Arizona
    {
        "name": "Schnebly Hill Road",
        "region": "Sedona, Arizona",
        "difficulty": 3,
        "distance_miles": 12.0,
        "highway_approach_miles": 6.0,
        "estimated_hours": 2.5,
        "min_tire_inches": 30.0,
        "min_clearance_inches": 9.0,
        "requires_4lo": True,
        "min_lockers": 0,
        "requires_winch": False,
        "nearest_fuel": "Sedona, AZ",
        "camping": "Schnebly Hill Vista USFS dispersed camping",
        "flash_flood_sensitive": False,
        "summary": "Rocky red-rock climb from Sedona up to the Mogollon Rim.",
    },
    {
        "name": "Broken Arrow Trail",
        "region": "Sedona, Arizona",
        "difficulty": 5,
        "distance_miles": 4.0,
        "highway_approach_miles": 4.0,
        "estimated_hours": 2.0,
        "min_tire_inches": 32.0,
        "min_clearance_inches": 10.0,
        "requires_4lo": True,
        "min_lockers": 1,
        "requires_winch": False,
        "nearest_fuel": "Sedona, AZ",
        "camping": "Forest Road 525 dispersed camping (Coconino NF)",
        "flash_flood_sensitive": False,
        "summary": "Famous Sedona slickrock trail featuring Submarine Rock and the Devil's Staircase.",
    },
]


FALLBACK_WEATHER_BY_REGION: dict[str, dict[str, Any]] = {
    "moab": {
        "resolved_location": "Moab, Grand County, Utah, USA",
        "elevation_feet": 4025,
        "high_temp_f": 78.0,
        "low_temp_f": 48.0,
        "precip_probability_percent": 15,
        "max_wind_mph": 14.0,
        "flash_flood_risk": "MODERATE — Desert washes (Onion Creek, Shafer Basin, Kane Creek) flood rapidly if upstream storms develop.",
        "alpine_snow_ice_risk": "NONE",
    },
    "colorado": {
        "resolved_location": "Silverton / Ouray (San Juan Mountains), Colorado, USA",
        "elevation_feet": 11800,
        "high_temp_f": 52.0,
        "low_temp_f": 26.0,
        "precip_probability_percent": 35,
        "max_wind_mph": 24.0,
        "flash_flood_risk": "LOW",
        "alpine_snow_ice_risk": "HIGH — Sub-freezing overnight temperatures above 11,000 ft; watch for snow drifts and black ice on shelf roads.",
    },
    "sierra": {
        "resolved_location": "Rubicon / Lake Tahoe Basin, Sierra Nevada, California, USA",
        "elevation_feet": 7050,
        "high_temp_f": 64.0,
        "low_temp_f": 34.0,
        "precip_probability_percent": 20,
        "max_wind_mph": 16.0,
        "flash_flood_risk": "LOW",
        "alpine_snow_ice_risk": "MODERATE — Cold mountain nights near 7,000+ ft; verify seasonal gate status on high Sierra passes.",
    },
    "death valley": {
        "resolved_location": "Furnace Creek / Death Valley National Park, California, USA",
        "elevation_feet": 190,
        "high_temp_f": 96.0,
        "low_temp_f": 66.0,
        "precip_probability_percent": 5,
        "max_wind_mph": 18.0,
        "flash_flood_risk": "MODERATE — Narrow canyons (Titus Canyon, Goler Wash) must never be entered during rain.",
        "alpine_snow_ice_risk": "NONE",
    },
    "sedona": {
        "resolved_location": "Sedona, Coconino County, Arizona, USA",
        "elevation_feet": 4350,
        "high_temp_f": 81.0,
        "low_temp_f": 52.0,
        "precip_probability_percent": 10,
        "max_wind_mph": 12.0,
        "flash_flood_risk": "LOW",
        "alpine_snow_ice_risk": "NONE",
    },
}


def search_curated_trails(region: str, max_difficulty: int) -> dict[str, Any]:
    """Searches the curated catalog of 4x4 trails by region or trail name and maximum difficulty.

    Args:
        region: Destination region or trail keyword (e.g. 'Moab', 'Sierra', 'Rubicon', 'Colorado', 'Sedona', 'Death Valley').
        max_difficulty: Maximum trail technical difficulty rating to filter by on a 1 to 10 scale (use 10 to see all trails in the region).

    Returns:
        Dictionary containing 'status', 'matching_trails' (within max_difficulty), and 'harder_trails_in_region' (above max_difficulty for reference).
    """
    query = region.strip().lower()
    region_matches: list[dict[str, Any]] = []

    for trail in CURATED_TRAILS:
        haystack = f"{trail['name']} {trail['region']} {trail['summary']}".lower()
        if query in haystack or any(
            token in haystack for token in query.split() if len(token) >= 3
        ):
            region_matches.append(trail)

    if not region_matches:
        region_matches = list(CURATED_TRAILS)

    compatible = [t for t in region_matches if t["difficulty"] <= max_difficulty]
    harder = [t for t in region_matches if t["difficulty"] > max_difficulty]

    return {
        "status": "success",
        "queried_region": region,
        "max_difficulty_filter": max_difficulty,
        "matching_trails_count": len(compatible),
        "matching_trails": compatible,
        "harder_trails_in_region": harder,
    }


def check_rig_trail_compatibility(
    trail_name: str,
    trail_difficulty: int,
    tire_size_inches: float,
    clearance_inches: float,
    has_4lo: bool,
    lockers: int,
    has_winch: bool,
    is_solo: bool,
) -> dict[str, Any]:
    """Deterministically evaluates whether a user's 4x4 vehicle is safe for a given trail difficulty (1-10).

    Args:
        trail_name: Name of the 4x4 trail being evaluated.
        trail_difficulty: Technical trail rating on a 1 to 10 scale.
        tire_size_inches: Tire diameter in inches (e.g. 29.0 for AWD crossover, 31.0 for stock 4x4, 33.0-37.0 for modified).
        clearance_inches: Minimum ground clearance in inches (e.g. 8.7 for Outback, 9.6 for 4Runner, 10.8+ for lifted 4x4).
        has_4lo: True if the vehicle has a true two-speed transfer case with 4WD Low range (False for AWD crossovers).
        lockers: Number of locking differentials (0 = open/traction control only, 1 = rear locker, 2 = front and rear lockers).
        has_winch: True if the vehicle has a front recovery winch installed.
        is_solo: True if traveling in a single vehicle without a second recovery buddy vehicle.

    Returns:
        Dictionary with 'is_compatible', 'max_safe_difficulty', 'trail_difficulty', 'blocking_reasons', and 'safety_warnings'.
    """
    blocking_reasons: list[str] = []
    safety_warnings: list[str] = []

    # Compute deterministic max_safe_difficulty (1-10)
    if not has_4lo:
        if clearance_inches >= 8.0 and tire_size_inches >= 28.0:
            max_safe_difficulty = 2
        else:
            max_safe_difficulty = 1
    else:
        max_safe_difficulty = 3
        if tire_size_inches >= 31.0 and clearance_inches >= 9.0:
            max_safe_difficulty = 4
        if tire_size_inches >= 32.0 and clearance_inches >= 9.8 and lockers >= 1:
            max_safe_difficulty = 5
        if tire_size_inches >= 33.0 and clearance_inches >= 10.5 and lockers >= 1:
            max_safe_difficulty = 6
        if tire_size_inches >= 35.0 and clearance_inches >= 11.0 and lockers >= 2:
            max_safe_difficulty = 8 if has_winch else 7
        if (
            tire_size_inches >= 37.0
            and clearance_inches >= 12.0
            and lockers >= 2
            and has_winch
        ):
            max_safe_difficulty = 9
        if (
            tire_size_inches >= 40.0
            and clearance_inches >= 13.5
            and lockers >= 2
            and has_winch
        ):
            max_safe_difficulty = 10

    is_compatible = trail_difficulty <= max_safe_difficulty

    if not is_compatible:
        if not has_4lo and trail_difficulty >= 3:
            blocking_reasons.append(
                f"HARD SAFETY BLOCK: Vehicle lacks a 4WD Low-range (4Lo) transfer case. AWD vehicles are capped at 2/10 graded dirt roads and cannot safely climb or engine-brake on {trail_name} ({trail_difficulty}/10)."
            )
        if trail_difficulty >= 4 and (
            tire_size_inches < 31.0 or clearance_inches < 9.0
        ):
            blocking_reasons.append(
                f'Insufficient clearance/tires: {trail_name} ({trail_difficulty}/10) requires at least 31-inch tires and 9.0+ inches of ground clearance (vehicle has {tire_size_inches}" tires and {clearance_inches}" clearance).'
            )
        if trail_difficulty >= 5 and lockers < 1:
            blocking_reasons.append(
                f'Missing traction aid: Trails rated {trail_difficulty}/10 require at least 1 locking differential (rear locker), 32-33"+ tires, and 10"+ clearance.'
            )
        if trail_difficulty >= 7 and (
            tire_size_inches < 35.0 or clearance_inches < 11.0 or lockers < 2
        ):
            blocking_reasons.append(
                f'Extreme trail mismatch: {trail_name} ({trail_difficulty}/10) requires 35"+ tires, 11"+ ground clearance, and front + rear locking differentials (2 lockers).'
            )
        if trail_difficulty >= 8 and not has_winch:
            blocking_reasons.append(
                f"Missing mandatory winch: {trail_name} ({trail_difficulty}/10) requires a heavy-duty recovery winch."
            )
        if trail_difficulty >= 9 and tire_size_inches < 37.0:
            blocking_reasons.append(
                f'Buggy/extreme rock-crawler territory: {trail_name} ({trail_difficulty}/10) requires 37"+ tires, dual lockers, and a winch.'
            )

    if trail_difficulty >= 6 and is_solo:
        safety_warnings.append(
            f"SOLO TRAVEL WARNING: {trail_name} is rated {trail_difficulty}/10. Traveling solo on trails rated 6/10 or higher carries severe stranding risk; travel with a second 4x4 vehicle and carry a satellite communicator (e.g. Garmin inReach)."
        )
    if trail_difficulty >= 6 and not has_winch:
        safety_warnings.append(
            f"RECOVERY WARNING: {trail_name} ({trail_difficulty}/10) is attempted without a winch. Carry traction boards, a kinetic recovery rope, soft shackles, and travel with a winch-equipped partner."
        )
    if trail_difficulty >= 3:
        safety_warnings.append(
            "Air down tires to 15-20 PSI for off-road traction and sidewall protection, and carry a 12V air compressor + tire plug kit."
        )

    return {
        "status": "success",
        "trail_name": trail_name,
        "trail_difficulty": trail_difficulty,
        "max_safe_difficulty": max_safe_difficulty,
        "is_compatible": is_compatible,
        "verdict": "APPROVED" if is_compatible else "REJECTED_UNSAFE_FOR_RIG",
        "blocking_reasons": blocking_reasons,
        "safety_warnings": safety_warnings,
    }


def calculate_offroad_fuel_plan(
    highway_miles: float,
    offroad_miles: float,
    trail_difficulty: int,
    highway_mpg: float,
    tank_capacity_gallons: float,
) -> dict[str, Any]:
    """Calculates off-road and highway fuel consumption and enforces the mandatory 25% backcountry reserve margin.

    Args:
        highway_miles: Paved highway approach and return miles between fuel stops for the leg.
        offroad_miles: Dirt/rock trail miles between fuel stops for the leg.
        trail_difficulty: Technical trail difficulty rating (1-10) used to determine the off-road 4Lo MPG penalty.
        highway_mpg: Vehicle's rated highway fuel economy in miles per gallon (MPG).
        tank_capacity_gallons: Vehicle's total fuel tank capacity in US gallons.

    Returns:
        Dictionary containing estimated off-road MPG, total fuel needed, tank percentage used, 25% reserve compliance status, and required auxiliary fuel (jerry cans).
    """
    safe_highway_mpg = max(1.0, highway_mpg)
    safe_tank = max(1.0, tank_capacity_gallons)

    # Off-road terrain and 4Lo gearing reduces fuel economy significantly
    if trail_difficulty <= 2:
        mpg_multiplier = 0.75
    elif trail_difficulty <= 4:
        mpg_multiplier = 0.55
    elif trail_difficulty <= 6:
        mpg_multiplier = 0.45
    else:
        mpg_multiplier = 0.35

    estimated_offroad_mpg = round(safe_highway_mpg * mpg_multiplier, 2)
    highway_fuel_gallons = highway_miles / safe_highway_mpg
    offroad_fuel_gallons = offroad_miles / estimated_offroad_mpg
    total_fuel_needed_gallons = round(highway_fuel_gallons + offroad_fuel_gallons, 2)

    usable_75_percent_budget_gallons = round(safe_tank * 0.75, 2)
    mandatory_25_percent_reserve_gallons = round(safe_tank * 0.25, 2)
    tank_utilization_percent = round((total_fuel_needed_gallons / safe_tank) * 100.0, 1)

    meets_reserve_rule = total_fuel_needed_gallons <= usable_75_percent_budget_gallons
    auxiliary_fuel_required_gallons = round(
        max(0.0, total_fuel_needed_gallons - usable_75_percent_budget_gallons), 2
    )
    recommended_5gal_jerry_cans = (
        math.ceil(auxiliary_fuel_required_gallons / 5.0)
        if auxiliary_fuel_required_gallons > 0
        else 0
    )

    if meets_reserve_rule:
        advisory = (
            f"PASS: Leg consumes {total_fuel_needed_gallons} gal ({tank_utilization_percent}% of {safe_tank}-gal tank), "
            f"staying within the 75% usable budget ({usable_75_percent_budget_gallons} gal) and preserving at least a 25% reserve ({mandatory_25_percent_reserve_gallons} gal)."
        )
    else:
        advisory = (
            f"FUEL RESERVE WARNING: Leg requires {total_fuel_needed_gallons} gal ({tank_utilization_percent}% of {safe_tank}-gal tank), "
            f"which exceeds the 75% usable backcountry budget ({usable_75_percent_budget_gallons} gal) and violates the mandatory 25% reserve rule ({mandatory_25_percent_reserve_gallons} gal reserve). "
            f"You MUST carry at least {auxiliary_fuel_required_gallons} gallons of auxiliary fuel ({recommended_5gal_jerry_cans}x 5-gallon jerry can / RotopaX) or refuel mid-route."
        )

    return {
        "status": "success",
        "highway_miles": highway_miles,
        "offroad_miles": offroad_miles,
        "total_leg_miles": round(highway_miles + offroad_miles, 1),
        "highway_mpg": safe_highway_mpg,
        "estimated_offroad_mpg": estimated_offroad_mpg,
        "total_fuel_needed_gallons": total_fuel_needed_gallons,
        "tank_capacity_gallons": safe_tank,
        "usable_75_percent_budget_gallons": usable_75_percent_budget_gallons,
        "mandatory_25_percent_reserve_gallons": mandatory_25_percent_reserve_gallons,
        "tank_utilization_percent": tank_utilization_percent,
        "meets_25_percent_reserve_rule": meets_reserve_rule,
        "auxiliary_fuel_required_gallons": auxiliary_fuel_required_gallons,
        "recommended_5gal_jerry_cans": recommended_5gal_jerry_cans,
        "fuel_safety_status": (
            "SAFE_WITHIN_75_PERCENT_BUDGET"
            if meets_reserve_rule
            else "WARNING_EXCEEDS_75_PERCENT_BUDGET_AUX_FUEL_REQUIRED"
        ),
        "advisory": advisory,
    }


def get_trail_weather_and_elevation(location_name: str) -> dict[str, Any]:
    """Fetches weather forecast, elevation, flash-flood risk, and alpine snow/ice advisories for a trail or region.

    Uses OpenStreetMap Nominatim and Open-Meteo keyless APIs, with reliable regional backcountry baselines if offline.

    Args:
        location_name: Trail region or town name (e.g. 'Moab, Utah', 'Silverton, Colorado', 'Lake Tahoe, California').

    Returns:
        Dictionary with elevation, temperature range, precipitation probability, wind speed, flash-flood risk, and trail weather advisories.
    """
    loc_lower = location_name.strip().lower()

    try:
        encoded_q = urllib.parse.quote(location_name)
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={encoded_q}&format=json&limit=1"
        req = urllib.request.Request(
            geocode_url,
            headers={"User-Agent": "ADK-FourByFourTripPlanner/1.0"},
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))

        if geo_data:
            lat = float(geo_data[0]["lat"])
            lon = float(geo_data[0]["lon"])
            resolved_name = geo_data[0].get("display_name", location_name)

            meteo_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"
                f"&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto&forecast_days=3"
            )
            meteo_req = urllib.request.Request(
                meteo_url,
                headers={"User-Agent": "ADK-FourByFourTripPlanner/1.0"},
            )
            with urllib.request.urlopen(meteo_req, timeout=4.0) as m_resp:
                meteo = json.loads(m_resp.read().decode("utf-8"))

            elevation_m = float(meteo.get("elevation", 1200.0))
            elevation_ft = round(elevation_m * 3.28084)
            daily = meteo.get("daily", {})
            highs = daily.get("temperature_2m_max", [75.0])
            lows = daily.get("temperature_2m_min", [45.0])
            precips = daily.get("precipitation_probability_max", [15])
            winds = daily.get("wind_speed_10m_max", [12.0])

            max_high_f = round(max(highs), 1)
            min_low_f = round(min(lows), 1)
            max_precip_prob = int(max(precips))
            max_wind_mph = round(max(winds), 1)

            is_desert = any(
                k in loc_lower
                for k in [
                    "moab",
                    "utah",
                    "death valley",
                    "canyon",
                    "sedona",
                    "arizona",
                    "mojave",
                ]
            )
            if max_precip_prob >= 40:
                flash_flood_risk = f"HIGH ({max_precip_prob}% precip chance) — Avoid slot canyons, creek crossings (e.g. Onion Creek), and desert washes!"
            elif is_desert:
                flash_flood_risk = f"MODERATE ({max_precip_prob}% precip chance) — Desert washes flood from distant storms; monitor NOAA alerts before entering canyons."
            else:
                flash_flood_risk = f"LOW ({max_precip_prob}% precip chance)"

            if elevation_ft >= 8500 or min_low_f <= 32.0:
                alpine_risk = f"ELEVATED (Elevation {elevation_ft} ft, overnight low {min_low_f}°F) — Pack cold-weather emergency gear and check for snow/ice on high passes."
            else:
                alpine_risk = "NONE"

            return {
                "status": "success",
                "source": "live_open_meteo",
                "queried_location": location_name,
                "resolved_location": resolved_name,
                "elevation_feet": elevation_ft,
                "three_day_high_temp_f": max_high_f,
                "three_day_low_temp_f": min_low_f,
                "max_precip_probability_percent": max_precip_prob,
                "max_wind_mph": max_wind_mph,
                "flash_flood_risk": flash_flood_risk,
                "alpine_snow_ice_risk": alpine_risk,
            }
    except Exception:
        pass

    # Fallback regional backcountry profile if external network is unavailable
    selected = FALLBACK_WEATHER_BY_REGION["moab"]
    for key, profile in FALLBACK_WEATHER_BY_REGION.items():
        if (
            key in loc_lower
            or (
                key == "sierra"
                and any(
                    w in loc_lower
                    for w in ["tahoe", "rubicon", "california", "fordyce"]
                )
            )
            or (
                key == "colorado"
                and any(
                    w in loc_lower
                    for w in ["ouray", "silverton", "telluride", "imogene", "alpine"]
                )
            )
        ):
            selected = profile
            break

    return {
        "status": "success",
        "source": "regional_backcountry_baseline",
        "queried_location": location_name,
        "resolved_location": selected["resolved_location"],
        "elevation_feet": selected["elevation_feet"],
        "three_day_high_temp_f": selected["high_temp_f"],
        "three_day_low_temp_f": selected["low_temp_f"],
        "max_precip_probability_percent": selected["precip_probability_percent"],
        "max_wind_mph": selected["max_wind_mph"],
        "flash_flood_risk": selected["flash_flood_risk"],
        "alpine_snow_ice_risk": selected["alpine_snow_ice_risk"],
        "note": "Verify live local NOAA / USFS / BLM ranger station conditions prior to trailhead departure.",
    }
