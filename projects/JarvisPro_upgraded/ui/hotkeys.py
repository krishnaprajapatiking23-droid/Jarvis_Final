"""Configurable global hotkeys (deep-spec section 12).

The manager owns parsing, normalisation, conflict detection and dispatch. The
actual OS key grab is a provider, so the logic is testable with no desktop
session and honestly reports NOT_CONFIGURED when no backend is installed.
"""

import threading
from typing import Any, Callable, Dict, List, Optional

OK = "ok"
INVALID = "invalid_input"
CONFLICT = "conflict"
NOT_FOUND = "not_found"
NOT_CONFIGURED = "NOT_CONFIGURED"
UNAVAILABLE = "UNAVAILABLE"

MODIFIERS = ("ctrl", "alt", "shift", "meta")
_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
    "meta": "meta", "cmd": "meta", "command": "meta", "win": "meta",
    "super": "meta",
}
_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "meta": "Meta"}
_NAMED_KEYS = {
    "space": "Space", "tab": "Tab", "enter": "Enter", "return": "Enter",
    "escape": "Escape", "esc": "Escape", "delete": "Delete", "del": "Delete",
    "backspace": "Backspace", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown", "insert": "Insert",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "plus": "Plus", "minus": "Minus", "comma": "Comma", "period": "Period",
}
RESERVED = ("ctrl+alt+delete", "ctrl+shift+escape", "alt+tab", "meta+l")


def _key_label(token: str) -> Optional[str]:
    if token in _NAMED_KEYS:
        return _NAMED_KEYS[token]
    if len(token) == 1 and (token.isalnum()):
        return token.upper()
    if token.startswith("f") and token[1:].isdigit():
        number = int(token[1:])
        if 1 <= number <= 24:
            return "F%d" % number
    return None


def normalise(raw: Any):
    """Return (ok, canonical_binding, reason)."""
    if not isinstance(raw, str) or not raw.strip():
        return False, None, "a hotkey must be a non-empty string"
    tokens = [part.strip().lower()
              for part in raw.replace("-", "+").split("+")]
    if any(not token for token in tokens):
        return False, None, "hotkey %r has an empty component" % raw
    mods: List[str] = []
    keys: List[str] = []
    for token in tokens:
        if token in _MODIFIER_ALIASES:
            mod = _MODIFIER_ALIASES[token]
            if mod not in mods:
                mods.append(mod)
        else:
            keys.append(token)
    if not keys:
        return False, None, "hotkey %r has no main key" % raw
    if len(keys) > 1:
        return False, None, "hotkey %r has more than one main key" % raw
    if not mods:
        return False, None, ("hotkey %r needs at least one modifier so it does "
                             "not steal a plain keypress" % raw)
    label = _key_label(keys[0])
    if label is None:
        return False, None, "%r is not a key this platform can bind" % keys[0]
    canonical_parts = [m for m in MODIFIERS if m in mods] + [keys[0]]
    if "+".join(canonical_parts) in RESERVED:
        return False, None, "%s is reserved by the operating system" % raw
    display = "+".join([_LABELS[m] for m in MODIFIERS if m in mods] + [label])
    return True, display, None


class HotkeyProvider:
    """Port for an OS key-grab backend."""

    name = "base"

    def register(self, binding: str, action: str) -> None:
        raise NotImplementedError

    def unregister(self, binding: str) -> None:
        raise NotImplementedError


class NullHotkeyProvider(HotkeyProvider):
    name = "null"

    def register(self, binding: str, action: str) -> None:
        raise RuntimeError("no global hotkey backend installed")

    def unregister(self, binding: str) -> None:
        raise RuntimeError("no global hotkey backend installed")


class HotkeyManager:
    capability = "ui_hotkeys"

    def __init__(self, provider: Optional[HotkeyProvider] = None) -> None:
        self.provider = provider or NullHotkeyProvider()
        self._lock = threading.RLock()
        self._bindings: Dict[str, Dict[str, Any]] = {}
        self.fired = 0
        self.failures = 0

    # ---- backend ----
    def set_provider(self, provider: HotkeyProvider) -> Dict[str, Any]:
        with self._lock:
            self.provider = provider
            rebound: List[str] = []
            errors: Dict[str, str] = {}
            for binding, entry in self._bindings.items():
                try:
                    provider.register(binding, entry["action"])
                    entry["registered"] = True
                    rebound.append(binding)
                except Exception as exc:
                    entry["registered"] = False
                    errors[binding] = str(exc)
        return {"status": OK, "provider": getattr(provider, "name", "custom"),
                "rebound": rebound, "errors": errors}

    # ---- bindings ----
    def bind(self, keys: Any, action: str, handler: Optional[Callable] = None,
             replace: bool = False) -> Dict[str, Any]:
        ok, binding, reason = normalise(keys)
        if not ok:
            return {"status": INVALID, "error": reason}
        if not isinstance(action, str) or not action.strip():
            return {"status": INVALID, "error": "an action name is required"}
        with self._lock:
            existing = self._bindings.get(binding)
            if existing and not replace and existing["action"] != action:
                return {"status": CONFLICT, "binding": binding,
                        "error": "%s is already bound to %s"
                                 % (binding, existing["action"])}
            entry = {"action": action.strip(), "handler": handler,
                     "registered": False, "fired": 0}
            self._bindings[binding] = entry
            try:
                self.provider.register(binding, entry["action"])
                entry["registered"] = True
            except Exception as exc:
                return {"status": NOT_CONFIGURED, "binding": binding,
                        "error": "hotkey tracked but not grabbed: %s" % exc}
        return {"status": OK, "binding": binding, "action": entry["action"]}

    def unbind(self, keys: Any) -> Dict[str, Any]:
        ok, binding, reason = normalise(keys)
        if not ok:
            return {"status": INVALID, "error": reason}
        with self._lock:
            entry = self._bindings.pop(binding, None)
            if entry is None:
                return {"status": NOT_FOUND, "binding": binding}
            try:
                self.provider.unregister(binding)
            except Exception:
                pass
        return {"status": OK, "binding": binding, "action": entry["action"]}

    def rebind(self, action: str, keys: Any) -> Dict[str, Any]:
        ok, binding, reason = normalise(keys)
        if not ok:
            return {"status": INVALID, "error": reason}
        with self._lock:
            current = [b for b, e in self._bindings.items()
                       if e["action"] == action]
            if not current:
                return {"status": NOT_FOUND, "action": action}
            taken = self._bindings.get(binding)
            if taken and taken["action"] != action:
                return {"status": CONFLICT, "binding": binding,
                        "error": "%s is already bound to %s"
                                 % (binding, taken["action"])}
            entry = self._bindings.pop(current[0])
            try:
                self.provider.unregister(current[0])
            except Exception:
                pass
            self._bindings[binding] = entry
            try:
                self.provider.register(binding, action)
                entry["registered"] = True
            except Exception as exc:
                entry["registered"] = False
                return {"status": NOT_CONFIGURED, "binding": binding,
                        "error": "hotkey moved but not grabbed: %s" % exc}
        return {"status": OK, "action": action, "binding": binding,
                "previous": current[0]}

    def bindings(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {binding: {"action": entry["action"],
                              "registered": entry["registered"],
                              "has_handler": entry["handler"] is not None,
                              "fired": entry["fired"]}
                    for binding, entry in self._bindings.items()}

    # ---- dispatch ----
    def trigger(self, keys: Any) -> Dict[str, Any]:
        ok, binding, reason = normalise(keys)
        if not ok:
            return {"status": INVALID, "error": reason}
        with self._lock:
            entry = self._bindings.get(binding)
        if entry is None:
            return {"status": NOT_FOUND, "binding": binding}
        handler = entry["handler"]
        if handler is None:
            return {"status": NOT_CONFIGURED, "binding": binding,
                    "error": "%s has no handler attached" % entry["action"]}
        try:
            result = handler()
        except Exception as exc:
            self.failures += 1
            return {"status": "failure", "binding": binding,
                    "action": entry["action"], "error": str(exc)}
        entry["fired"] += 1
        self.fired += 1
        return {"status": OK, "binding": binding, "action": entry["action"],
                "result": result}

    def health(self) -> Dict[str, Any]:
        with self._lock:
            bound = len(self._bindings)
            registered = sum(1 for e in self._bindings.values()
                             if e["registered"])
        backend = getattr(self.provider, "name", "custom")
        available = backend != "null" and (registered > 0 or bound == 0)
        return {"available": available,
                "status": OK if available else NOT_CONFIGURED,
                "provider": backend, "bound": bound, "registered": registered,
                "fired": self.fired, "failures": self.failures,
                "reason": None if available else
                "no global hotkey backend has grabbed the configured keys"}
