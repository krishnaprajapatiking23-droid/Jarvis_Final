"""Persistent, validated UI settings (deep-spec section 13).

Settings live in SQLite, not one big JSON blob: each key is a row, every write
is validated against a declared schema, and every change is journalled so the
settings panel can show history and so a bad value can be traced.
"""

import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .hotkeys import normalise

OK = "ok"
INVALID = "invalid_input"
NOT_FOUND = "not_found"

THEMES = ("arc_reactor", "midnight", "light")
MODES = ("standard", "focus", "ultra")
START_PAGES = ("dashboard", "chat", "voice", "automation", "memory", "files",
               "system", "settings")


class Setting:
    """One declared setting: kind, default, bounds and help text."""

    KINDS = ("bool", "int", "float", "choice", "path", "hotkey", "text")

    def __init__(self, key: str, kind: str, default: Any, label: str,
                 choices: Any = (), minimum: Any = None, maximum: Any = None,
                 max_chars: int = 120, restart_required: bool = False) -> None:
        self.key = key
        self.kind = kind
        self.default = default
        self.label = label
        self.choices = tuple(choices)
        self.minimum = minimum
        self.maximum = maximum
        self.max_chars = max_chars
        self.restart_required = restart_required

    def describe(self) -> Dict[str, Any]:
        return {"key": self.key, "kind": self.kind, "default": self.default,
                "label": self.label, "choices": list(self.choices),
                "min": self.minimum, "max": self.maximum,
                "restart_required": self.restart_required}

    def validate(self, value: Any):
        """Return (ok, coerced_value, error)."""
        if self.kind == "bool":
            if isinstance(value, bool):
                return True, value, None
            if isinstance(value, str) and value.strip().lower() in (
                    "true", "false", "yes", "no", "on", "off"):
                return True, value.strip().lower() in ("true", "yes", "on"), None
            return False, None, "%s expects true or false" % self.key
        if self.kind in ("int", "float"):
            if isinstance(value, bool):
                return False, None, "%s expects a number" % self.key
            try:
                number = int(value) if self.kind == "int" else float(value)
            except Exception:
                return False, None, "%s expects a number, got %r" % (self.key, value)
            if self.minimum is not None and number < self.minimum:
                return False, None, "%s must be >= %s" % (self.key, self.minimum)
            if self.maximum is not None and number > self.maximum:
                return False, None, "%s must be <= %s" % (self.key, self.maximum)
            return True, number, None
        if self.kind == "choice":
            if isinstance(value, str) and value in self.choices:
                return True, value, None
            return False, None, "%s must be one of %s" % (
                self.key, ", ".join(self.choices))
        if self.kind == "hotkey":
            ok, normalised, reason = normalise(value)
            if not ok:
                return False, None, "%s is not a valid hotkey: %s" % (self.key, reason)
            return True, normalised, None
        if self.kind == "path":
            import os
            if not isinstance(value, str) or not value.strip():
                return False, None, "%s expects a path" % self.key
            if not os.path.isdir(value):
                return False, None, "%s must point at an existing directory" % self.key
            return True, value, None
        if not isinstance(value, str):
            return False, None, "%s expects text" % self.key
        text = value.strip()
        if not text:
            return False, None, "%s must not be empty" % self.key
        if len(text) > self.max_chars:
            return False, None, "%s must be %d characters or fewer" % (
                self.key, self.max_chars)
        return True, text, None


SCHEMA: Dict[str, Setting] = {s.key: s for s in (
    Setting("theme", "choice", "arc_reactor", "Theme", choices=THEMES),
    Setting("mode", "choice", "standard", "Assistant mode", choices=MODES),
    Setting("start_page", "choice", "dashboard", "Page on launch",
            choices=START_PAGES),
    Setting("telemetry_interval_ms", "int", 1000, "Telemetry refresh (ms)",
            minimum=250, maximum=60000),
    Setting("global_hotkey", "hotkey", "Ctrl+Shift+J", "Show/hide JARVIS"),
    Setting("push_to_talk_hotkey", "hotkey", "Ctrl+Shift+Space", "Push to talk"),
    Setting("wake_word", "text", "jarvis", "Wake word", max_chars=32),
    Setting("voice_enabled", "bool", True, "Voice replies"),
    Setting("toast_seconds", "float", 6.0, "Notification duration",
            minimum=1, maximum=60),
    Setting("minimise_to_tray", "bool", True, "Minimise to tray"),
    Setting("launch_on_login", "bool", False, "Launch on login",
            restart_required=True),
    Setting("animations", "bool", True, "Animated arc reactor"),
    Setting("owner_name", "text", "the owner", "Owner name", max_chars=60),
)}


class SettingsStore:
    capability = "ui_settings"

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS settings ("
                         "key TEXT PRIMARY KEY, value TEXT, updated REAL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS settings_log ("
                         "id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, "
                         "old TEXT, new TEXT, at REAL)")
        self._db.commit()
        self._listeners: List[Callable[[str, Any, Any], None]] = []
        self.rejected = 0

    # ---- schema ----
    def schema(self) -> List[Dict[str, Any]]:
        return [SCHEMA[key].describe() for key in sorted(SCHEMA)]

    def on_change(self, callback: Callable[[str, Any, Any], None]) -> None:
        self._listeners.append(callback)

    # ---- reads ----
    def get(self, key: str) -> Any:
        setting = SCHEMA.get(key)
        if setting is None:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return setting.default
        try:
            stored = json.loads(row[0])
        except Exception:
            # A corrupt row must not break the UI; fall back to the default.
            return setting.default
        ok, value, _ = setting.validate(stored)
        return value if ok else setting.default

    def all(self) -> Dict[str, Any]:
        return {key: self.get(key) for key in sorted(SCHEMA)}

    # ---- writes ----
    def set(self, key: str, value: Any) -> Dict[str, Any]:
        setting = SCHEMA.get(key)
        if setting is None:
            return {"status": NOT_FOUND, "key": key,
                    "error": "unknown setting %r" % key}
        ok, coerced, error = setting.validate(value)
        if not ok:
            self.rejected += 1
            return {"status": INVALID, "key": key, "error": error}
        old = self.get(key)
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO settings (key, value, updated) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated = excluded.updated",
                (key, json.dumps(coerced), now))
            self._db.execute(
                "INSERT INTO settings_log (key, old, new, at) VALUES (?,?,?,?)",
                (key, json.dumps(old), json.dumps(coerced), now))
            self._db.commit()
        for listener in list(self._listeners):
            try:
                listener(key, old, coerced)
            except Exception:
                pass  # a broken observer must not undo a valid write
        return {"status": OK, "key": key, "value": coerced, "previous": old,
                "restart_required": setting.restart_required}

    def update(self, values: Dict[str, Any]) -> Dict[str, Any]:
        applied: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for key, value in (values or {}).items():
            result = self.set(key, value)
            if result["status"] == OK:
                applied[key] = result["value"]
            else:
                errors[key] = result["error"]
        return {"status": OK if not errors else INVALID, "applied": applied,
                "errors": errors,
                "restart_required": any(SCHEMA[k].restart_required
                                        for k in applied)}

    def reset(self, key: str) -> Dict[str, Any]:
        if key not in SCHEMA:
            return {"status": NOT_FOUND, "key": key}
        return self.set(key, SCHEMA[key].default)

    def history(self, key: Optional[str] = None,
                limit: int = 50) -> List[Dict[str, Any]]:
        query = ("SELECT key, old, new, at FROM settings_log %s"
                 "ORDER BY id DESC LIMIT ?"
                 % ("WHERE key = ? " if key else ""))
        params: Any = (key, int(limit)) if key else (int(limit),)
        with self._lock:
            rows = self._db.execute(query, params).fetchall()

        def load(raw: Any) -> Any:
            try:
                return json.loads(raw)
            except Exception:
                return raw

        return [{"key": row[0], "old": load(row[1]), "new": load(row[2]),
                 "at": row[3]} for row in rows]

    def health(self) -> Dict[str, Any]:
        with self._lock:
            stored = self._db.execute(
                "SELECT COUNT(*) FROM settings").fetchone()[0]
            changes = self._db.execute(
                "SELECT COUNT(*) FROM settings_log").fetchone()[0]
        return {"available": True, "status": OK, "declared": len(SCHEMA),
                "stored": stored, "changes": changes,
                "rejected": self.rejected, "path": self.db_path}

    def close(self) -> None:
        with self._lock:
            try:
                self._db.commit()
                self._db.close()
            except Exception:
                pass
