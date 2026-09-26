"""Settings panel.

Tkinter is optional. Importing this module never fails: when tkinter is not
installed, :func:`available` returns False and :meth:`build` explains what to
install instead of raising ImportError at import time -- which is how
``gui/test_gui.py`` used to take the whole GUI package down.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = ["SettingsPanel", "settings_panel", "available"]

try:
    import tkinter as tk
    from tkinter import ttk
    _TK_ERROR = ""
except Exception as _error:
    tk = None
    ttk = None
    _TK_ERROR = "%s: %s" % (type(_error).__name__, _error)


def available() -> bool:
    """True when a tkinter GUI can actually be built here."""
    return tk is not None


class SettingsPanel:
    """Settings panel."""

    title = "Settings panel"

    def __init__(self, master: Any = None):
        self.master = master
        self.widget = None

    def build(self, master: Any = None) -> Dict[str, Any]:
        """Create the widget, or report why it cannot be created."""
        if not available():
            return {"success": False, "widget": None,
                    "error": "tkinter is not installed (%s); "
                             "install python3-tk to use the desktop UI"
                             % _TK_ERROR}

        parent = master or self.master or tk.Tk()
        frame = ttk.Frame(parent, padding=8)
        frame.pack(fill="both", expand=True)
        self._populate(frame)
        self.widget = frame
        return {"success": True, "widget": frame, "error": ""}

    def _populate(self, frame: Any) -> None:
        ttk.Label(frame, text=self.title).pack(anchor="w")

    def destroy(self) -> None:
        if self.widget is not None:
            try:
                self.widget.destroy()
            except Exception:
                pass
            self.widget = None

    def status(self) -> Dict[str, Any]:
        return {"available": available(), "built": self.widget is not None,
                "detail": _TK_ERROR}


settings_panel = SettingsPanel()
