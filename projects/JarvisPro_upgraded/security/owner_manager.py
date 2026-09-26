"""
Owner lookup.

Reads ``data/owner.json`` when it exists and falls back to the shared
identity resolver (``config/settings.json`` -> ``core.config``) so a
missing or damaged owner file can no longer crash the assistant.
"""

import json
import logging
import os

log = logging.getLogger("jarvis.security.owner")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_FILE = os.path.join(PROJECT_ROOT, "data", "owner.json")


def load_owner():
    """The owner record as a dict.  Empty dict when it cannot be read."""
    try:
        if os.path.exists(OWNER_FILE):
            with open(OWNER_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                return data
    except Exception as error:
        log.debug("owner.json unreadable: %s", error)
    return {}


def owner_name():
    """The configured owner name, or "" when nobody is configured."""
    name = str(load_owner().get("name", "") or "").strip()
    if name:
        return name

    try:
        from conversation.identity import identity

        return identity.owner()
    except Exception as error:  # pragma: no cover - defensive
        log.debug("identity lookup failed: %s", error)
        return ""


def is_owner(username):
    """True when ``username`` matches the configured owner."""
    owner = owner_name()
    if not owner or not username:
        return False
    return username.strip().casefold() == owner.strip().casefold()
