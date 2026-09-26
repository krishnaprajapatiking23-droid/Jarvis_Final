"""
JARVIS PRO - configuration package.

The single entry point for every setting, API key and service endpoint used
anywhere in JARVIS:

    from config import config

    config.get("voice.enabled", True)
    config.api_key("gemini")
    config.has("openrouter")

Adapted from the portable config loaders of the reference projects
(ULTRON utils/env.py + config/__init__.py, Mark-LII memory/config_manager.py,
Mark-XXXIX-OR config/), merged into one system so no module has to know where
settings live.
"""

from .manager import config, ConfigManager

__all__ = [
    "config",
    "ConfigManager",
]
