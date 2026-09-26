"""Automation package with lazy optional desktop backends.

BUG FIX: the previous ``__getattr__`` here never actually ran for these
names. As soon as anything imports the submodule -- e.g. ``.desktop`` --
Python's import machinery binds that submodule object directly onto this
package (``automation.desktop = <module 'automation.desktop'>``), which
satisfies ``hasattr(automation, "desktop")`` and so module-level
``__getattr__`` (PEP 562) is skipped entirely for that name from then on.
Since every one of these submodules is named after the singleton it
defines (``automation/desktop.py`` defines ``desktop = Desktop()``), a plain
``from automation import desktop`` silently returned the *module*, not the
*singleton* -- and the module has no ``open_desktop`` method, only the class
inside it does. That produced
``AttributeError: module 'automation.desktop' has no attribute 'open_desktop'``
in manual_demos/demo_sprint_a1.py.

The fix is to import each submodule eagerly, once, right here, and bind the
singleton itself (not the module) as this package's attribute -- so
``automation.desktop`` is always the ``Desktop()`` instance, never the module
it lives in, and ``hasattr``/``getattr``/``from automation import desktop``
all agree.
"""

import importlib
import logging

log = logging.getLogger("jarvis.automation")

__all__ = [
    "desktop", "power", "screenshots", "volume",
    "clipboard", "processes", "windows", "system_info",
]

_SOURCES = {
    "desktop": (".desktop", "desktop"),
    "power": (".power", "power"),
    "screenshots": (".screenshots", "screenshots"),
    "volume": (".volume", "volume"),
    "clipboard": (".clipboard", "clipboard"),
    "processes": (".process", "processes"),
    "windows": (".window_manager", "windows"),
    "system_info": (".system_info", "system_info"),
}


class _Unavailable:
    """Stands in for a backend whose optional dependency is missing.

    Any attribute access raises the *original* import error rather than a
    generic AttributeError, so the real cause (e.g. "no module named
    pyautogui") is what the caller sees.
    """

    def __init__(self, name: str, error: Exception):
        self._name = name
        self._error = error

    def __getattr__(self, attribute: str):
        raise RuntimeError(
            "automation.%s is unavailable: %s" % (self._name, self._error)
        ) from self._error

    def __repr__(self) -> str:
        return "<automation.%s unavailable: %s>" % (self._name, self._error)

    def __bool__(self) -> bool:
        return False


for _name, (_module, _attribute) in _SOURCES.items():
    try:
        _imported = importlib.import_module(_module, __name__)
        globals()[_name] = getattr(_imported, _attribute)
    except Exception as _error:  # a missing optional dependency, e.g. pyautogui
        log.info("automation.%s unavailable: %s", _name, _error)
        globals()[_name] = _Unavailable(_name, _error)

del importlib, logging, log, _SOURCES, _Unavailable
