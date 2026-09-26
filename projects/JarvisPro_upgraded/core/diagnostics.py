"""
==========================================
JARVIS PRO
Self-diagnostics
==========================================

Roadmap section 39 (health checks, self-test, "why did that fail?").

One call that answers "is JARVIS healthy?":

    from core.diagnostics import diagnostics

    diagnostics.run()      # full machine-readable report
    diagnostics.summary()  # one paragraph, ready to speak

Every probe is wrapped, so a broken subsystem is reported as a finding
instead of crashing the diagnostic run.
"""

from __future__ import annotations

import importlib
import platform
import sys
import time
from typing import Any, Callable

from config import config
from core.observability import observability


# Optional third-party packages and what stops working without them.
OPTIONAL_PACKAGES = {
    "psutil": "system telemetry",
    "requests": "http helpers",
    "bs4": "richer web-search parsing",
    "ollama": "local model access",
    "pyttsx3": "offline speech output",
    "speech_recognition": "speech input",
    "cv2": "vision features",
    "pyautogui": "desktop automation",
}

# Internal modules that must import cleanly.
CORE_MODULES = [
    "config",
    "core.observability",
    "core.model_router",
    "core.tool_schema",
    "core.undo_manager",
    "core.backup_manager",
    "core.plugin_loader",
    "security.policy_engine",
    "core.system_monitor",
    "internet.search_engine",
    "brains_v2.agent.planner",
    "brains_v2.agent.executor",
    "brains_v2.agent.task_queue",
    "brains_v2.agent.error_handler",
]


class Diagnostics:

    def _probe(self, name: str, function: Callable[[], Any]) -> dict[str, Any]:
        started = time.time()

        try:
            return {
                "name": name,
                "ok": True,
                "elapsed": round(time.time() - started, 3),
                "detail": function(),
            }

        except Exception as error:
            return {
                "name": name,
                "ok": False,
                "elapsed": round(time.time() - started, 3),
                "detail": f"{type(error).__name__}: {error}",
            }

    # ---------------------------------------------------- probes

    def _environment(self) -> dict[str, Any]:
        return {
            "python": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}",
            "project": str(config.path()),
        }

    def _packages(self) -> dict[str, Any]:
        present: list[str] = []
        missing: list[dict[str, str]] = []

        for package, purpose in OPTIONAL_PACKAGES.items():
            try:
                importlib.import_module(package)
                present.append(package)

            except Exception:
                missing.append({"package": package, "affects": purpose})

        return {"installed": present, "missing": missing}

    def _modules(self) -> dict[str, Any]:
        broken: list[dict[str, str]] = []

        for name in CORE_MODULES:
            try:
                importlib.import_module(name)

            except Exception as error:
                broken.append({"module": name, "error": f"{type(error).__name__}: {error}"})

        return {
            "checked": len(CORE_MODULES),
            "broken": broken,
            "healthy": len(CORE_MODULES) - len(broken),
        }

    def _models(self) -> dict[str, Any]:
        from core.model_router import router

        health = router.health()

        return {
            "offline_first": health["offline_first"],
            "capabilities": health["capabilities"],
            "model_count": len(health["models"]),
            "models": [
                {
                    "model": item["model"],
                    "provider": item["provider"],
                    "available": item["available"],
                }
                for item in health["models"]
            ],
        }

    def _services(self) -> dict[str, Any]:
        status = config.status()

        return {
            "configured": [
                name for name, item in status.items() if item["configured"]
            ],
            "not_configured": [
                {"service": name, "hint": item["hint"], "purpose": item["purpose"]}
                for name, item in status.items()
                if not item["configured"]
            ],
        }

    def _tools(self) -> dict[str, Any]:
        from core.tool_schema import tool_registry

        catalogue = tool_registry.catalogue()

        return {
            "total": len(catalogue),
            "runnable": sum(1 for item in catalogue if item["callable"]),
            "by_category": {
                category: sum(
                    1 for item in catalogue if item["category"] == category
                )
                for category in sorted({item["category"] for item in catalogue})
            },
        }

    def _plugins(self) -> dict[str, Any]:
        from core.plugin_loader import plugins

        status = plugins.status()

        return {
            "loaded": status["loaded"],
            "broken": status["broken"],
            "names": [item["name"] for item in status["plugins"]],
        }

    def _system(self) -> dict[str, Any]:
        from core.system_monitor import monitor

        data = monitor.snapshot()

        return {
            "telemetry": data.get("psutil", False),
            "cpu": data.get("cpu", {}).get("percent"),
            "ram": data.get("ram", {}).get("percent"),
            "disk_free_gb": data.get("disk", {}).get("free_gb"),
        }

    def _reliability(self) -> dict[str, Any]:
        health = observability.health()

        return {
            "total_runs": health["total_runs"],
            "success_rate": health["success_rate"],
            "recent_errors": health["recent_errors"],
            "weakest": health["worst"][:3],
        }

    def _storage(self) -> dict[str, Any]:
        from core.backup_manager import backup

        return backup.status()

    # ---------------------------------------------------- running

    def run(self) -> dict[str, Any]:
        """Full diagnostic sweep."""

        checks = [
            self._probe("environment", self._environment),
            self._probe("internal modules", self._modules),
            self._probe("optional packages", self._packages),
            self._probe("models", self._models),
            self._probe("external services", self._services),
            self._probe("tools", self._tools),
            self._probe("plugins", self._plugins),
            self._probe("system", self._system),
            self._probe("reliability", self._reliability),
            self._probe("backups", self._storage),
        ]

        failed = [check["name"] for check in checks if not check["ok"]]

        report = {
            "at": time.time(),
            "healthy": not failed,
            "failed_checks": failed,
            "checks": checks,
        }

        observability.info(
            "diagnostics",
            "diagnostic run finished",
            healthy=report["healthy"],
            failed=failed,
        )

        return report

    def summary(self) -> str:
        """Spoken-style summary of the sweep."""

        report = self.run()
        detail = {check["name"]: check for check in report["checks"]}

        lines: list[str] = []

        modules = detail.get("internal modules", {}).get("detail", {})

        if isinstance(modules, dict):
            broken = modules.get("broken") or []

            lines.append(
                f"{modules.get('healthy', 0)}/{modules.get('checked', 0)} "
                "core modules import cleanly"
                + (f", {len(broken)} broken" if broken else "")
            )

        models = detail.get("models", {}).get("detail", {})

        if isinstance(models, dict):
            lines.append(f"{models.get('model_count', 0)} models routable")

        tools = detail.get("tools", {}).get("detail", {})

        if isinstance(tools, dict):
            lines.append(
                f"{tools.get('runnable', 0)} of {tools.get('total', 0)} tools runnable"
            )

        reliability = detail.get("reliability", {}).get("detail", {})

        if isinstance(reliability, dict) and reliability.get("total_runs"):
            lines.append(
                f"success rate {reliability.get('success_rate', 0) * 100:.0f}%"
            )

        services = detail.get("external services", {}).get("detail", {})

        if isinstance(services, dict) and services.get("not_configured"):
            names = ", ".join(
                item["service"] for item in services["not_configured"]
            )
            lines.append(f"optional services not configured: {names}")

        state = "All systems nominal." if report["healthy"] else (
            "Some checks failed: " + ", ".join(report["failed_checks"]) + "."
        )

        return state + " " + "; ".join(lines) + "."


diagnostics = Diagnostics()
