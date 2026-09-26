"""Skill manager (roadmap section 16).

Single place that asks every registered skill and plugin whether it can answer
a command. Both registries were previously dead on import; this manager is the
supported way to reach them.
"""

from __future__ import annotations

from typing import Any, Dict, List

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["SkillManager", "skill_manager"]


class SkillManager(BaseManager):
    capability = "skills"
    description = "Routes a command to the first skill or plugin that fits."

    def _skills(self) -> List[Any]:
        try:
            from brains_v2.skills.registry import all_skills

            return list(all_skills())
        except Exception:
            return []

    def _plugins(self) -> List[Any]:
        try:
            from plugins.plugin_loader import load_plugins

            return list(load_plugins())
        except Exception:
            return []

    def catalogue(self) -> List[Dict[str, str]]:
        """Every capability currently discoverable, for capability discovery."""
        found: List[Dict[str, str]] = []
        for kind, items in (("skill", self._skills()), ("plugin", self._plugins())):
            for item in items:
                found.append({
                    "kind": kind,
                    "name": getattr(item, "name", type(item).__name__),
                    "description": getattr(item, "description", ""),
                })
        return found

    def can_handle(self, command: Any) -> bool:
        for item in self._skills() + self._plugins():
            try:
                if item.can_handle(command):
                    return True
            except Exception:
                continue
        return False

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        for item in self._skills() + self._plugins():
            try:
                if not item.can_handle(command):
                    continue
                outcome = item.execute(command)
            except Exception as error:
                return ManagerResult(
                    False, "%s failed: %s" % (getattr(item, "name", "skill"), error))

            if outcome is None:
                continue

            if isinstance(outcome, dict):
                return ManagerResult(
                    bool(outcome.get("success", True)),
                    outcome.get("reply", str(outcome)),
                    skill=getattr(item, "name", ""), raw=outcome,
                )

            return ManagerResult(True, str(outcome),
                                 skill=getattr(item, "name", ""))

        return ManagerResult(False, "", handled=False)

    def health(self) -> Dict[str, Any]:
        count = len(self._skills()) + len(self._plugins())
        return {
            "available": count > 0,
            "capability": self.capability,
            "detail": "%d skill(s)/plugin(s) registered" % count,
        }


skill_manager = SkillManager()
