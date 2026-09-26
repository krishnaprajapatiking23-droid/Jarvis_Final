"""Weather API facade. Delegates to the weather skill."""

from __future__ import annotations

from typing import Any, Dict

from skills.weather import weather_skill

__all__ = ["current", "configured"]


def configured() -> bool:
    return weather_skill.configured()


def current(place: str = "") -> Dict[str, Any]:
    query = "weather in %s" % place if place else "weather"
    return weather_skill.execute(query)
