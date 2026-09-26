"""Project manager (roadmap section 16).

Tracks the projects the user is working on, which files belong to them and
which is currently active, persisted as JSON so it survives a restart.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["ProjectManager", "project_manager"]

STORE = os.path.join("data", "projects.json")

_CREATE = re.compile(
    r"^(?:please\s+)?(?:create|add|start|new)\s+(?:a\s+)?project\s+"
    r"(?:called\s+|named\s+)?(?P<name>.+)$", re.IGNORECASE)
_LIST = re.compile(r"^(?:please\s+)?(?:show|list|what\s+are)\s*(?:me\s+)?"
                   r"(?:my\s+|all\s+)?projects?[?.!]*$", re.IGNORECASE)
_SWITCH = re.compile(r"^(?:please\s+)?(?:switch\s+to|open|work\s+on|use)\s+"
                     r"(?:the\s+)?project\s+(?P<name>.+)$", re.IGNORECASE)


class ProjectManager(BaseManager):
    capability = "projects"
    description = "Creates, lists and switches between the user's projects."

    def __init__(self, path: Optional[str] = None):
        self.path = path or STORE
        self._data: Dict[str, Any] = {"projects": {}, "active": None}
        self.load()

    # -- persistence -------------------------------------------------
    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return self._data
        if isinstance(stored, dict) and "projects" in stored:
            self._data = stored
        elif isinstance(stored, list):
            self._data = {"projects": {p: {} for p in stored}, "active": None}
        self._data.setdefault("projects", {})
        self._data.setdefault("active", None)
        return self._data

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

    # -- operations --------------------------------------------------
    def create(self, name: str, path: str = "", description: str = "") -> Dict[str, Any]:
        name = str(name).strip()
        if not name:
            return {"success": False, "error": "a project needs a name"}
        if name in self._data["projects"]:
            return {"success": False, "error": "project %r already exists" % name}
        self._data["projects"][name] = {
            "path": path,
            "description": description,
            "files": [],
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        self._data["active"] = name
        self.save()
        return {"success": True, "project": name}

    def list(self) -> List[str]:
        return sorted(self._data["projects"])

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self._data["projects"].get(name)

    def switch(self, name: str) -> Dict[str, Any]:
        if name not in self._data["projects"]:
            return {"success": False, "error": "no project called %r" % name}
        self._data["active"] = name
        self.save()
        return {"success": True, "active": name}

    def active(self) -> Optional[str]:
        return self._data.get("active")

    def add_file(self, name: str, file_path: str) -> Dict[str, Any]:
        project = self._data["projects"].get(name)
        if project is None:
            return {"success": False, "error": "no project called %r" % name}
        if file_path not in project["files"]:
            project["files"].append(file_path)
            self.save()
        return {"success": True, "files": project["files"]}

    def delete(self, name: str) -> Dict[str, Any]:
        if self._data["projects"].pop(name, None) is None:
            return {"success": False, "error": "no project called %r" % name}
        if self._data.get("active") == name:
            self._data["active"] = None
        self.save()
        return {"success": True}

    # -- manager interface -------------------------------------------
    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        return bool(_CREATE.match(text) or _LIST.match(text) or _SWITCH.match(text))

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        text = str(command or "").strip()

        match = _CREATE.match(text)
        if match:
            name = match.group("name").strip(" .?!")
            outcome = self.create(name)
            return ManagerResult(
                outcome["success"],
                "Project created: %s" % name if outcome["success"]
                else outcome["error"])

        match = _SWITCH.match(text)
        if match:
            name = match.group("name").strip(" .?!")
            outcome = self.switch(name)
            return ManagerResult(
                outcome["success"],
                "Now working on %s." % name if outcome["success"]
                else outcome["error"])

        if _LIST.match(text):
            names = self.list()
            if not names:
                return ManagerResult(True, "No projects yet.")
            active = self.active()
            lines = ["%d. %s%s" % (i, n, "  (active)" if n == active else "")
                     for i, n in enumerate(names, start=1)]
            return ManagerResult(True, "\n".join(lines))

        return ManagerResult(False, "", handled=False)

    def health(self) -> Dict[str, Any]:
        return {"available": True, "capability": self.capability,
                "detail": "%d project(s)" % len(self._data["projects"])}


project_manager = ProjectManager()
