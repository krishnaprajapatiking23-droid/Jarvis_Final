"""
==========================================
JARVIS PRO
Plugin system
==========================================

Roadmap section 36 (Developer / Jarvis maintenance: plugin architecture,
hot reload, feature flags).

Adapted from Mark-LII ``core/plugin_loader.py`` and reshaped for JARVIS:

  * a plugin is a single ``.py`` file inside ``plugins/`` that exposes a
    ``PLUGIN`` dict and a ``run(**kwargs)`` function;
  * names are validated and collisions are rejected, so a broken plugin can
    never shadow a built-in tool;
  * each plugin can be enabled/disabled from configuration (feature flags);
  * a failing plugin is isolated - it is marked broken with its error and
    JARVIS keeps running;
  * ``reload()`` re-imports from disk without restarting (hot reload).

Plugin file template:

    PLUGIN = {
        "name": "coin_flip",
        "description": "Flip a coin",
        "parameters": {"type": "OBJECT", "properties": {}},
    }

    def run(**kwargs):
        return "heads"
"""

from __future__ import annotations

import importlib.util
import re
import threading
import time
from pathlib import Path
from typing import Any

from config import config
from core.observability import observability


NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,39}$")

# Names a plugin may never take over.
RESERVED = {
    "run",
    "help",
    "exit",
    "quit",
    "shutdown",
    "restart",
    "config",
    "undo",
    "backup",
}


class Plugin:

    def __init__(self, path: Path, spec: dict[str, Any], handler: Any) -> None:
        self.path = path
        self.spec = spec
        self.handler = handler

        self.name = str(spec.get("name", path.stem)).strip().lower()
        self.description = str(spec.get("description", "")).strip()
        self.parameters = spec.get("parameters") or {
            "type": "OBJECT",
            "properties": {},
        }

        self.runs = 0
        self.failures = 0
        self.last_error = ""

    def enabled(self) -> bool:
        flags = config.get("plugins.enabled", None)

        if isinstance(flags, dict) and self.name in flags:
            return bool(flags[self.name])

        if isinstance(flags, list) and flags:
            return self.name in flags

        return True

    def run(self, **kwargs: Any) -> dict[str, Any]:
        if not self.enabled():
            return {
                "ok": False,
                "error": f"The plugin '{self.name}' is disabled.",
            }

        started = time.time()

        try:
            result = self.handler(**kwargs)

            self.runs += 1
            self.last_error = ""

            observability.record(
                f"plugin.{self.name}",
                time.time() - started,
                ok=True,
            )

            return {"ok": True, "result": result}

        except Exception as error:
            self.runs += 1
            self.failures += 1
            self.last_error = f"{type(error).__name__}: {error}"

            observability.record(
                f"plugin.{self.name}",
                time.time() - started,
                ok=False,
                error=self.last_error,
            )

            return {"ok": False, "error": self.last_error}

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "file": self.path.name,
            "enabled": self.enabled(),
            "runs": self.runs,
            "failures": self.failures,
            "last_error": self.last_error,
            "parameters": self.parameters,
        }


class PluginLoader:

    def __init__(self, folder: str = "plugins") -> None:
        self._lock = threading.RLock()
        self.folder = Path(str(config.path(folder)))
        self._plugins: dict[str, Plugin] = {}
        self._broken: dict[str, str] = {}
        self._loaded = False

    # ---------------------------------------------------- loading

    def _import(self, path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(
            f"jarvis_plugin_{path.stem}",
            path,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError("file could not be imported")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module

    def load(self, reserved: set[str] | None = None) -> dict[str, Any]:
        """Import every plugin file. Safe to call repeatedly."""

        reserved = (reserved or set()) | RESERVED

        with self._lock:
            self._plugins = {}
            self._broken = {}

            if not self.folder.exists():
                self._loaded = True

                return self.status()

            for path in sorted(self.folder.glob("*.py")):
                if path.name.startswith(("_", ".")):
                    continue

                try:
                    module = self._import(path)

                    spec = getattr(module, "PLUGIN", None)
                    handler = getattr(module, "run", None)

                    if not isinstance(spec, dict) or not callable(handler):
                        # A normal module in plugins/ - not a JARVIS plugin.
                        continue

                    plugin = Plugin(path, spec, handler)

                    if not NAME_PATTERN.match(plugin.name):
                        raise RuntimeError(
                            f"invalid plugin name '{plugin.name}' "
                            "(use lowercase letters, digits and underscores)"
                        )

                    if plugin.name in reserved:
                        raise RuntimeError(
                            f"'{plugin.name}' is a reserved name"
                        )

                    if plugin.name in self._plugins:
                        raise RuntimeError(
                            f"duplicate plugin name '{plugin.name}' "
                            f"(already provided by "
                            f"{self._plugins[plugin.name].path.name})"
                        )

                    self._plugins[plugin.name] = plugin

                except Exception as error:
                    self._broken[path.name] = f"{type(error).__name__}: {error}"

                    observability.warn(
                        "plugins",
                        f"failed to load {path.name}",
                        error=str(error),
                    )

            self._loaded = True

        return self.status()

    def reload(self) -> dict[str, Any]:
        """Hot reload - pick up new or edited plugin files."""

        return self.load()

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    # ---------------------------------------------------- using

    def names(self) -> list[str]:
        self._ensure()

        return sorted(self._plugins)

    def get(self, name: str) -> Plugin | None:
        self._ensure()

        return self._plugins.get(str(name).strip().lower())

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def run(self, name: str, /, **kwargs: Any) -> dict[str, Any]:
        plugin = self.get(name)

        if plugin is None:
            return {"ok": False, "error": f"There is no plugin called '{name}'."}

        return plugin.run(**kwargs)

    def enable(self, name: str, enabled: bool = True) -> bool:
        """Persist a feature flag for one plugin."""

        plugin = self.get(name)

        if plugin is None:
            return False

        flags = config.get("plugins.enabled", None)
        flags = dict(flags) if isinstance(flags, dict) else {}
        flags[plugin.name] = bool(enabled)

        config.set("plugins.enabled", flags)

        return True

    def disable(self, name: str) -> bool:
        return self.enable(name, False)

    # ---------------------------------------------------- reporting

    def declarations(self) -> list[dict[str, Any]]:
        """Tool declarations so plugins are callable by the model."""

        self._ensure()

        return [
            {
                "name": plugin.name,
                "description": plugin.description or f"Plugin {plugin.name}",
                "parameters": plugin.parameters,
                "source": "plugin",
            }
            for plugin in self._plugins.values()
            if plugin.enabled()
        ]

    def list_for_ui(self) -> list[dict[str, Any]]:
        self._ensure()

        return [plugin.report() for plugin in self._plugins.values()]

    def status(self) -> dict[str, Any]:
        return {
            "folder": str(self.folder),
            "loaded": len(self._plugins),
            "broken": dict(self._broken),
            "plugins": self.list_for_ui(),
        }


plugins = PluginLoader()
