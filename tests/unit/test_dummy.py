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
"""Unit tests for deterministic 4x4 trip planning tools and agent definitions."""

from app.agent import app, root_agent
from app.tools import (
    calculate_offroad_fuel_plan,
    check_rig_trail_compatibility,
    get_trail_weather_and_elevation,
    search_curated_trails,
)


def test_agent_and_app_definitions() -> None:
    """Verifies that root_agent and app are properly configured."""
    assert root_agent.name == "four_by_four_planner"
    assert app.name == "app"
    assert len(root_agent.tools) == 5


def test_search_curated_trails() -> None:
    """Verifies curated trail catalog filtering by region and max difficulty."""
    result = search_curated_trails(region="Moab", max_difficulty=4)
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
    assert res["is_compatible"] is False
    assert res["max_safe_difficulty"] == 2
    assert res["verdict"] == "REJECTED_UNSAFE_FOR_RIG"
    assert len(res["blocking_reasons"]) > 0


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
    assert res["is_compatible"] is True
    assert res["max_safe_difficulty"] >= 4
    assert res["verdict"] == "APPROVED"


def test_fuel_plan_enforces_25_percent_reserve_rule() -> None:
    """Verifies fuel consumption math and 25% reserve rule enforcement."""
    # Short leg: stays within 75% budget
    short_leg = calculate_offroad_fuel_plan(
        highway_miles=20.0,
        offroad_miles=15.0,
        trail_difficulty=3,
        highway_mpg=18.0,
        tank_capacity_gallons=23.0,
    )
    assert short_leg["meets_25_percent_reserve_rule"] is True
    assert short_leg["auxiliary_fuel_required_gallons"] == 0.0

    # Long remote traverse (White Rim 100mi offroad + 35mi highway on 17.5 gal tank @ 15 mpg)
    long_leg = calculate_offroad_fuel_plan(
        highway_miles=35.0,
        offroad_miles=100.0,
        trail_difficulty=4,
        highway_mpg=15.0,
        tank_capacity_gallons=17.5,
    )
    assert long_leg["meets_25_percent_reserve_rule"] is False
    assert long_leg["auxiliary_fuel_required_gallons"] > 0.0
    assert long_leg["recommended_5gal_jerry_cans"] >= 1


def test_weather_and_elevation_returns_valid_structure() -> None:
    """Verifies weather and elevation tool contract."""
    weather = get_trail_weather_and_elevation(location_name="Moab, Utah")
    assert weather["status"] == "success"
    assert "elevation_feet" in weather
    assert "flash_flood_risk" in weather
    assert "alpine_snow_ice_risk" in weather
