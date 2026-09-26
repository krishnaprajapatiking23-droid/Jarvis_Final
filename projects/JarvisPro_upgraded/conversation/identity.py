"""
==========================================
JARVIS PRO
Identity  (feature 3.5 support)
==========================================

Single source of truth for who JARVIS is talking to.

The owner name is read from ``config/settings.json`` (falling back to
``security.owner_manager`` and then ``core.config``) and is deliberately
NOT baked into response templates.  ``address()`` returns the name only
occasionally so replies do not stack the user's name on every turn.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.conversation.identity")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"
OWNER_FILE = PROJECT_ROOT / "data" / "owner.json"

DEFAULT_NAME = ""
ASSISTANT_NAME = "Jarvis"

# How often the user's name may appear in a reply (1 in N turns).
ADDRESS_EVERY = 5


class Identity:
    """Resolves the owner name and decides when to use it."""

    def __init__(self) -> None:
        self._cache: Optional[str] = None
        self._turns_since_address = 0

    # ------------------------------------------------------------------
    def settings(self) -> Dict[str, Any]:
        try:
            if SETTINGS_FILE.exists():
                with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if isinstance(data, dict):
                        return data
        except Exception as error:
            log.debug("settings.json unreadable: %s", error)
        return {}

    # ------------------------------------------------------------------
    def owner(self, refresh: bool = False) -> str:
        """The configured owner name, or "" when none is configured."""
        if self._cache is not None and not refresh:
            return self._cache

        name = str(self.settings().get("owner", "") or "").strip()

        if not name:
            try:
                if OWNER_FILE.exists():
                    with OWNER_FILE.open("r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    if isinstance(data, dict):
                        name = str(data.get("name", "") or "").strip()
            except Exception as error:
                log.debug("owner.json unreadable: %s", error)

        if not name:
            try:  # pragma: no cover - depends on host project state
                from core.config import OWNER_NAME  # type: ignore

                name = str(OWNER_NAME or "").strip()
            except Exception:
                name = DEFAULT_NAME

        self._cache = name
        return name

    # ------------------------------------------------------------------
    def assistant(self) -> str:
        return str(self.settings().get("wake_word", ASSISTANT_NAME) or ASSISTANT_NAME)

    # ------------------------------------------------------------------
    def address(self, force: bool = False, chance: bool = True) -> str:
        """Return the owner name when it is appropriate to use it.

        Returns "" most turns so replies stay natural.  ``force=True`` is
        used for genuine greetings and farewells.
        """
        name = self.owner()
        if not name:
            return ""

        if force:
            self._turns_since_address = 0
            return name

        self._turns_since_address += 1
        if self._turns_since_address < ADDRESS_EVERY:
            return ""
        if chance and random.random() > 0.5:
            return ""

        self._turns_since_address = 0
        return name

    # ------------------------------------------------------------------
    def suffix(self, force: bool = False) -> str:
        """", Krishna" style suffix, or "" when the name should be omitted."""
        name = self.address(force=force)
        return f", {name}" if name else ""

    def reset(self) -> None:
        self._cache = None
        self._turns_since_address = ADDRESS_EVERY


identity = Identity()

__all__ = ["Identity", "identity", "ASSISTANT_NAME", "ADDRESS_EVERY"]
