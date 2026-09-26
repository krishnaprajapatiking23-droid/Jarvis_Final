"""
==========================================
JARVIS PRO
Tool registry & capability schema
==========================================

Roadmap section 1 (tool registry, manager capability registry) and the
foundation of tool-calling for section 35.

Adapted from ULTRON ``core/tool_declarations.py``: a single catalogue that
describes every capability JARVIS has, in the JSON-schema shape that models
expect. Sources merged here:

  * the existing ``brains_v2.tools.registry`` / ``tools.registry``
  * plugins discovered by ``core.plugin_loader``
  * built-in declarations defined below

Each entry carries the policy action name, so the executor can ask
``security.policy_engine`` before running anything.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from core.observability import observability


def _schema(**properties: Any) -> dict[str, Any]:
    required = [
        name
        for name, spec in properties.items()
        if isinstance(spec, dict) and spec.pop("required", False)
    ]

    return {
        "type": "OBJECT",
        "properties": properties,
        "required": required,
    }


def _text(description: str, required: bool = False) -> dict[str, Any]:
    return {"type": "STRING", "description": description, "required": required}


@dataclass
class ToolSpec:
    name: str
    description: str
    action: str
    category: str
    parameters: dict[str, Any] = field(default_factory=lambda: _schema())
    source: str = "builtin"
    handler: Callable[..., Any] | None = None

    def declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "action": self.action,
            "source": self.source,
            "callable": self.handler is not None,
        }


# ---------------------------------------------------------------- built-ins

BUILTIN: list[ToolSpec] = [
    ToolSpec(
        "system_status",
        "Report CPU, memory, disk, temperature, GPU and battery state.",
        "system.info",
        "system",
        _schema(),
    ),
    ToolSpec(
        "top_processes",
        "List the processes using the most memory.",
        "system.info",
        "system",
        _schema(limit={"type": "INTEGER", "description": "How many rows."}),
    ),
    ToolSpec(
        "web_search",
        "Search the web and return summarised results.",
        "web.search",
        "research",
        _schema(
            query=_text("What to search for.", True),
            mode=_text("search, news, research, price or compare."),
        ),
    ),
    ToolSpec(
        "undo_last",
        "Undo the last reversible action JARVIS performed.",
        "self.modify",
        "maintenance",
        _schema(),
    ),
    ToolSpec(
        "create_backup",
        "Create a versioned backup of configuration and data.",
        "file.write",
        "maintenance",
        _schema(label=_text("Why the backup is taken.")),
    ),
    ToolSpec(
        "diagnostics",
        "Run a self-check of models, services, plugins and recent failures.",
        "system.info",
        "maintenance",
        _schema(),
    ),
]


class ToolRegistry:
    """Single source of truth for "what can JARVIS actually do"."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, ToolSpec] = {}
        self._built = False

    # ---------------------------------------------------- building

    def _add(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in self._tools:
            return

        self._tools[spec.name] = spec

    def _load_builtin(self) -> None:
        for spec in BUILTIN:
            self._add(
                ToolSpec(
                    spec.name,
                    spec.description,
                    spec.action,
                    spec.category,
                    spec.parameters,
                    spec.source,
                    self._builtin_handler(spec.name),
                )
            )

    def _builtin_handler(self, name: str) -> Callable[..., Any] | None:
        def system_status(**_: Any) -> Any:
            from core.system_monitor import monitor

            return monitor.report()

        def top_processes(limit: int = 5, **_: Any) -> Any:
            from core.system_monitor import monitor

            return monitor.top_processes(int(limit))

        def web_search(query: str = "", mode: str = "search", **_: Any) -> Any:
            from internet.search_engine import search_engine

            return search_engine.run(query, mode)

        def undo_last(**_: Any) -> Any:
            from core.undo_manager import undo

            return undo.undo()

        def create_backup(label: str = "manual", **_: Any) -> Any:
            from core.backup_manager import backup

            return backup.create(label)

        def diagnostics(**_: Any) -> Any:
            from core.diagnostics import diagnostics as run

            return run.run()

        return {
            "system_status": system_status,
            "top_processes": top_processes,
            "web_search": web_search,
            "undo_last": undo_last,
            "create_backup": create_backup,
            "diagnostics": diagnostics,
        }.get(name)

    def _load_existing(self) -> None:
        """Pick up the tools the project already ships, without duplicating."""

        for module_name in ("brains_v2.tools.registry", "tools.registry"):
            try:
                module = __import__(module_name, fromlist=["*"])

            except Exception:
                continue

            candidates: dict[str, Any] = {}

            for attribute in ("TOOLS", "REGISTRY", "registry", "tools"):
                value = getattr(module, attribute, None)

                if isinstance(value, dict):
                    candidates.update(value)

                elif hasattr(value, "all") and callable(getattr(value, "all")):
                    try:
                        found = value.all()

                        if isinstance(found, dict):
                            candidates.update(found)

                    except Exception:
                        pass

            for name, entry in candidates.items():
                handler = entry if callable(entry) else getattr(entry, "run", None)

                description = (
                    getattr(entry, "description", "")
                    or (handler.__doc__ or "").strip().split("\n")[0]
                    or f"Existing JARVIS tool '{name}'."
                )

                self._add(
                    ToolSpec(
                        str(name),
                        description[:300],
                        str(getattr(entry, "action", "") or f"tool.{name}"),
                        "existing",
                        _schema(
                            input=_text("Free-form input for this tool."),
                        ),
                        module_name,
                        handler if callable(handler) else None,
                    )
                )

    def _load_plugins(self) -> None:
        try:
            from core.plugin_loader import plugins

        except Exception:
            return

        for declaration in plugins.declarations():
            name = str(declaration["name"])

            self._add(
                ToolSpec(
                    name,
                    str(declaration.get("description", "")),
                    f"plugin.{name}",
                    "plugin",
                    dict(declaration.get("parameters") or _schema()),
                    "plugin",
                    lambda _name=name, **kwargs: plugins.run(_name, **kwargs),
                )
            )

    def build(self, force: bool = False) -> None:
        with self._lock:
            if self._built and not force:
                return

            self._tools = {}

            self._load_builtin()
            self._load_existing()
            self._load_plugins()

            self._built = True

        observability.info("tool_registry", "registry built", tools=len(self._tools))

    def refresh(self) -> None:
        self.build(force=True)

    # ---------------------------------------------------- reading

    def names(self) -> list[str]:
        self.build()

        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        self.build()

        return self._tools.get(str(name).strip())

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def declarations(self, category: str = "") -> list[dict[str, Any]]:
        self.build()

        return [
            spec.declaration()
            for spec in self._tools.values()
            if not category or spec.category == category
        ]

    def catalogue(self) -> list[dict[str, Any]]:
        self.build()

        return [spec.report() for spec in self._tools.values()]

    def summary(self, limit: int = 40) -> str:
        """Compact text block for planner prompts."""

        self.build()

        lines = [
            f"- {spec.name}: {spec.description}"
            for spec in list(self._tools.values())[:limit]
        ]

        return "\n".join(lines)

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        action: str = "",
        category: str = "custom",
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        """Let a manager add a capability at runtime."""

        self.build()

        with self._lock:
            if name in self._tools:
                return False

            self._tools[name] = ToolSpec(
                name,
                description,
                action or f"tool.{name}",
                category,
                parameters or _schema(),
                "runtime",
                handler,
            )

        return True

    # ---------------------------------------------------- running

    def run(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Run a tool through the policy engine and the observability layer."""

        spec = self.get(name)

        if spec is None:
            return {"ok": False, "error": f"There is no tool called '{name}'."}

        if spec.handler is None:
            return {
                "ok": False,
                "error": f"The tool '{name}' is declared but has no handler.",
            }

        try:
            from security.policy_engine import policy

            decision = policy.check(spec.action, dict(kwargs))

            if not decision.allowed:
                return {
                    "ok": False,
                    "error": decision.reason,
                    "needs_confirmation": decision.needs_confirmation,
                    "risk": decision.risk,
                    "action": spec.action,
                }

        except Exception:
            pass

        try:
            with observability.span(f"tool.{name}"):
                result = spec.handler(**kwargs)

            return {"ok": True, "result": result, "tool": name}

        except Exception as error:
            return {
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
                "tool": name,
            }


tool_registry = ToolRegistry()
