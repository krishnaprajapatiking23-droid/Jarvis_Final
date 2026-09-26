"""System tray menu (deep-spec section 11/12).

The menu model lives here; the actual tray icon is a provider. Without a
backend the menu is still fully usable programmatically and reports
NOT_CONFIGURED rather than pretending an icon appeared.
"""

import threading
from typing import Any, Callable, Dict, List, Optional

OK = "ok"
INVALID = "invalid_input"
NOT_FOUND = "not_found"
NOT_CONFIGURED = "NOT_CONFIGURED"


class TrayProvider:
    """Port for a real tray backend."""

    name = "base"

    def show(self, tooltip: str, menu: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def update(self, tooltip: str, menu: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def hide(self) -> None:
        raise NotImplementedError


class NullTrayProvider(TrayProvider):
    name = "null"

    def show(self, tooltip: str, menu: List[Dict[str, Any]]) -> None:
        raise RuntimeError("no system tray backend installed")

    def update(self, tooltip: str, menu: List[Dict[str, Any]]) -> None:
        raise RuntimeError("no system tray backend installed")

    def hide(self) -> None:
        raise RuntimeError("no system tray backend installed")


class TrayMenu:
    capability = "ui_tray"

    def __init__(self, tooltip: str = "JARVIS",
                 provider: Optional[TrayProvider] = None) -> None:
        self.tooltip = tooltip
        self.provider = provider or NullTrayProvider()
        self._lock = threading.RLock()
        self._items: List[Dict[str, Any]] = []
        self.visible = False
        self.clicks = 0
        self.failures = 0

    # ---- menu model ----
    def add(self, item_id: str, label: str, handler: Optional[Callable] = None,
            checkable: bool = False, checked: bool = False,
            separator_after: bool = False) -> Dict[str, Any]:
        if not isinstance(item_id, str) or not item_id.strip():
            return {"status": INVALID, "error": "an item id is required"}
        if not isinstance(label, str) or not label.strip():
            return {"status": INVALID, "error": "an item label is required"}
        with self._lock:
            if any(item["id"] == item_id for item in self._items):
                return {"status": INVALID,
                        "error": "tray item %r already exists" % item_id}
            self._items.append({"id": item_id, "label": label.strip(),
                                "handler": handler, "enabled": True,
                                "checkable": bool(checkable),
                                "checked": bool(checked) if checkable else None,
                                "separator_after": bool(separator_after)})
        self._sync()
        return {"status": OK, "id": item_id}

    def remove(self, item_id: str) -> Dict[str, Any]:
        with self._lock:
            remaining = [i for i in self._items if i["id"] != item_id]
            if len(remaining) == len(self._items):
                return {"status": NOT_FOUND, "id": item_id}
            self._items = remaining
        self._sync()
        return {"status": OK, "id": item_id}

    def _find(self, item_id: str) -> Optional[Dict[str, Any]]:
        for item in self._items:
            if item["id"] == item_id:
                return item
        return None

    def set_enabled(self, item_id: str, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            item = self._find(item_id)
            if item is None:
                return {"status": NOT_FOUND, "id": item_id}
            item["enabled"] = bool(enabled)
        self._sync()
        return {"status": OK, "id": item_id, "enabled": bool(enabled)}

    def set_checked(self, item_id: str, checked: bool) -> Dict[str, Any]:
        with self._lock:
            item = self._find(item_id)
            if item is None:
                return {"status": NOT_FOUND, "id": item_id}
            if not item["checkable"]:
                return {"status": INVALID,
                        "error": "tray item %r is not checkable" % item_id}
            item["checked"] = bool(checked)
        self._sync()
        return {"status": OK, "id": item_id, "checked": bool(checked)}

    def set_tooltip(self, tooltip: str) -> Dict[str, Any]:
        if not isinstance(tooltip, str) or not tooltip.strip():
            return {"status": INVALID, "error": "a tooltip is required"}
        self.tooltip = tooltip.strip()
        self._sync()
        return {"status": OK, "tooltip": self.tooltip}

    def items(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{k: v for k, v in item.items() if k != "handler"}
                    for item in self._items]

    # ---- backend ----
    def set_provider(self, provider: TrayProvider) -> Dict[str, Any]:
        self.provider = provider
        return self.show()

    def show(self) -> Dict[str, Any]:
        try:
            self.provider.show(self.tooltip, self.items())
        except Exception as exc:
            self.visible = False
            return {"status": NOT_CONFIGURED, "error": str(exc),
                    "provider": getattr(self.provider, "name", "custom")}
        self.visible = True
        return {"status": OK, "provider": getattr(self.provider, "name", "custom")}

    def hide(self) -> Dict[str, Any]:
        try:
            self.provider.hide()
        except Exception as exc:
            return {"status": NOT_CONFIGURED, "error": str(exc)}
        self.visible = False
        return {"status": OK}

    def _sync(self) -> None:
        if not self.visible:
            return
        try:
            self.provider.update(self.tooltip, self.items())
        except Exception:
            self.visible = False

    # ---- dispatch ----
    def click(self, item_id: str) -> Dict[str, Any]:
        with self._lock:
            item = self._find(item_id)
            if item is None:
                return {"status": NOT_FOUND, "id": item_id}
            if not item["enabled"]:
                return {"status": INVALID,
                        "error": "tray item %r is disabled" % item_id}
            handler = item["handler"]
            checkable = item["checkable"]
        if handler is None:
            return {"status": NOT_CONFIGURED, "id": item_id,
                    "error": "tray item %r has no handler" % item_id}
        if checkable:
            with self._lock:
                item["checked"] = not bool(item["checked"])
            self._sync()
        try:
            result = handler()
        except Exception as exc:
            self.failures += 1
            return {"status": "failure", "id": item_id, "error": str(exc)}
        self.clicks += 1
        return {"status": OK, "id": item_id, "result": result,
                "checked": self._find(item_id)["checked"] if checkable else None}

    def health(self) -> Dict[str, Any]:
        backend = getattr(self.provider, "name", "custom")
        available = self.visible and backend != "null"
        return {"available": available,
                "status": OK if available else NOT_CONFIGURED,
                "provider": backend, "items": len(self._items),
                "clicks": self.clicks, "failures": self.failures,
                "reason": None if available else
                "no system tray backend is showing the JARVIS icon"}
