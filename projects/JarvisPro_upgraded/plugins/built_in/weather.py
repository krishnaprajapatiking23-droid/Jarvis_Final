"""Weather plugin.

This module was an empty placeholder. The capability it names already has a
single working implementation elsewhere in the project, so this file is a
documented adapter that re-exports it rather than a second copy that would
drift out of step. Import from here or from the canonical module -- both give
you the same object.

Canonical implementation: ``skills.weather``
"""

from __future__ import annotations

from skills.weather import WeatherSkill as WeatherPlugin, weather_skill as weather_plugin

__all__ = ["WeatherPlugin", "weather_plugin"]

