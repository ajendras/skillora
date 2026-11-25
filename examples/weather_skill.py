"""Weather lookup skill example for Skillora.

A complete, runnable skill that demonstrates:
- Proper use of the @skill decorator
- Mock API behavior (no real network calls)
- Consistent SkillResult contract
- Example test cases and a CLI-friendly main block

This skill can be tested with: skillora test examples/weather_skill.py
or run directly: python examples/weather_skill.py
"""

from __future__ import annotations

import json
from typing import Any, Dict

from skillora import Skill, SkillResult, skill


@skill(
    name="weather-lookup",
    description="Retrieves current weather conditions and temperature for a city using a mock backend.",
    version="0.2.0",
    tags=["weather", "api", "external-service"],
    author="Skillora Examples",
)
class WeatherSkill(Skill):
    """Weather lookup skill with deterministic mock responses.

    Supports context keys: location, city, or query.
    Returns structured weather data or a clear error.
    """

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        """Execute weather lookup.

        Args:
            context: Must contain one of: location, city, or query.

        Returns:
            SkillResult with weather data or error message.
        """
        # Normalize location input from multiple possible keys
        location = (
            context.get("location")
            or context.get("city")
            or context.get("query")
            or ""
        )
        location_str = str(location).strip().lower()

        if not location_str:
            return SkillResult(
                success=False,
                error="No location provided. Please supply 'location', 'city', or 'query' in context.",
                metadata={
                    "provided_keys": list(context.keys()),
                    "tip": "Try {'location': 'London'}",
                },
            )

        # Mock weather database
        mock_db = {
            "new york": {
                "temp_c": 16,
                "condition": "Partly Cloudy",
                "humidity": 62,
                "wind_kph": 14,
            },
            "london": {
                "temp_c": 11,
                "condition": "Light Rain",
                "humidity": 88,
                "wind_kph": 22,
            },
            "tokyo": {
                "temp_c": 24,
                "condition": "Clear",
                "humidity": 45,
                "wind_kph": 8,
            },
            "paris": {
                "temp_c": 19,
                "condition": "Sunny",
                "humidity": 53,
                "wind_kph": 11,
            },
        }

        data = mock_db.get(
            location_str,
            {
                "temp_c": 18,
                "condition": "Cloudy",
                "humidity": 60,
                "wind_kph": 12,
            },
        )

        output = {
            "location": location,
            "temperature_c": data["temp_c"],
            "condition": data["condition"],
            "humidity_percent": data["humidity"],
            "wind_kph": data["wind_kph"],
            "units": "metric",
            "source": "mock-weather-api-v1",
            "cached": False,
        }

        return SkillResult(
            success=True,
            output=output,
            metadata={
                "skill": "weather-lookup",
                "location_normalized": location_str,
                "mock": True,
                "response_time_ms": 12,
            },
        )


# Module-level instance required by CLI loader and for easy import
skill = WeatherSkill()


# ----------------------------------------------------------------------
# Example test cases used by both manual runs and the test generator
# ----------------------------------------------------------------------
EXAMPLE_TEST_CASES = [
    {"location": "New York"},
    {"city": "London"},
    {"query": "Tokyo"},
    {"location": "Paris"},
    {"city": "Unknown City"},  # triggers default mock data
    {"invalid": "no location key"},  # triggers error path
]


if __name__ == "__main__":
    print("WeatherSkill Demo")
    print("=" * 60)

    for i, case in enumerate(EXAMPLE_TEST_CASES, start=1):
        print(f"\nTest case {i}: {case}")
        result: SkillResult = skill.execute(case)

        print(f"Success : {result.success}")
        if result.success:
            print("Output  :")
            print(
                json.dumps(result.output, indent=2)
                .replace("\n", "\n          ")
            )
        else:
            print(f"Error   : {result.error}")
        print("-" * 60)

    print("\nWeather skill ready for use with LangGraph, CrewAI, or any Skillora runtime.")
    print("Run: skillora test examples/weather_skill.py")
