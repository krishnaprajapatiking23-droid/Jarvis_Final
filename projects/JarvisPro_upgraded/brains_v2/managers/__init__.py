"""Specialised managers (roadmap section 16).

Importing this package registers every available manager on a registry that
supports capability discovery, health probes and fallback selection. Each
manager import is guarded so one missing optional dependency cannot take the
whole registry down.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from brains_v2.managers.base import BaseManager, ManagerResult

log = logging.getLogger("jarvis.managers")

__all__ = ["BaseManager", "ManagerResult", "REGISTRY", "get", "names",
           "capabilities", "health", "select"]

REGISTRY: Dict[str, BaseManager] = {}


def _register(module_name: str, attribute: str) -> None:
    try:
        module = __import__("brains_v2.managers." + module_name,
                            fromlist=[attribute])
        manager = getattr(module, attribute)
        REGISTRY[manager.capability] = manager
    except Exception as error:
        log.info("manager %s unavailable: %s", module_name, error)


for _module, _attribute in (
    ("memory_manager", "memory_manager"),
    ("automation_manager", "automation_manager"),
    ("skill_manager", "skill_manager"),
    ("tool_manager", "tool_manager"),
    ("project_manager", "project_manager"),
    ("ai_manager", "ai_manager"),
    ("voice_manager", "voice_manager"),
):
    _register(_module, _attribute)


def get(capability: str) -> Optional[BaseManager]:
    return REGISTRY.get(capability)


def names() -> List[str]:
    return sorted(REGISTRY)


def capabilities() -> List[Dict[str, str]]:
    return [{"capability": name, "description": manager.description}
            for name, manager in sorted(REGISTRY.items())]


def health() -> Dict[str, Dict[str, Any]]:
    report: Dict[str, Dict[str, Any]] = {}
    for name, manager in REGISTRY.items():
        try:
            report[name] = manager.health()
        except Exception as error:
            report[name] = {"available": False, "capability": name,
                            "detail": "%s: %s" % (type(error).__name__, error)}
    return report


def select(command: Any) -> List[BaseManager]:
    """Every manager willing to take the command, in registration order."""
    chosen: List[BaseManager] = []
    for manager in REGISTRY.values():
        try:
            if manager.can_handle(command):
                chosen.append(manager)
        except Exception:
            continue
    return chosen
