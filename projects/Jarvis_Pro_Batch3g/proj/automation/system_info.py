"""System information with a stable public API (BUG 9).

Callers use ``system_info.summary()``. That works two ways now:

* ``from automation import system_info`` -> module, ``system_info.summary()``
  resolves to the module-level function below.
* ``from automation.system_info import system_info`` -> singleton instance,
  ``system_info.summary()`` resolves to the method.

Both return identical output, so the historical module/instance confusion
cannot produce an ``AttributeError`` any more. psutil is optional: without
it the metrics that need it are reported as unavailable instead of raising.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
from typing import Any, Dict, Optional

__all__ = [
    "SystemInfo",
    "system_info",
    "summary",
    "details",
    "metrics_available",
    "report",
    "info",
]

log = logging.getLogger(__name__)


def _load_psutil() -> Optional[Any]:
    try:
        import psutil
    except Exception as error:
        log.debug("psutil unavailable: %r", error)
        return None
    return psutil


class SystemInfo:
    """Collects host information for the assistant to read out."""

    def __init__(self) -> None:
        self._psutil = _load_psutil()

    # ------------------------------------------------------------- capability
    def metrics_available(self) -> bool:
        """True when live CPU/RAM metrics can be read (psutil present)."""
        return self._psutil is not None

    # ----------------------------------------------------------------- pieces
    def platform_details(self) -> Dict[str, Any]:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "hostname": socket.gethostname(),
        }

    def cpu(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"cores": os.cpu_count() or 0}
        if self._psutil is not None:
            try:
                data["percent"] = self._psutil.cpu_percent(interval=0.1)
            except Exception as error:
                data["error"] = f"{type(error).__name__}: {error}"
        else:
            data["percent"] = None
        return data

    def memory(self) -> Dict[str, Any]:
        if self._psutil is None:
            return {"available": False}
        try:
            virtual = self._psutil.virtual_memory()
            return {
                "available": True,
                "total_gb": round(virtual.total / (1024 ** 3), 2),
                "used_percent": virtual.percent,
            }
        except Exception as error:
            return {"available": False, "error": f"{type(error).__name__}: {error}"}

    def disk(self, path: str = "/") -> Dict[str, Any]:
        target = path if os.path.exists(path) else os.getcwd()
        try:
            usage = shutil.disk_usage(target)
            return {
                "path": target,
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
            }
        except Exception as error:
            return {"path": target, "error": f"{type(error).__name__}: {error}"}

    def battery(self) -> Dict[str, Any]:
        if self._psutil is None or not hasattr(self._psutil, "sensors_battery"):
            return {"available": False}
        try:
            state = self._psutil.sensors_battery()
        except Exception as error:
            return {"available": False, "error": f"{type(error).__name__}: {error}"}
        if state is None:
            return {"available": False}
        return {
            "available": True,
            "percent": state.percent,
            "plugged": bool(state.power_plugged),
        }

    # ------------------------------------------------------------- public API
    def details(self) -> Dict[str, Any]:
        """Full machine-readable snapshot."""
        return {
            "platform": self.platform_details(),
            "cpu": self.cpu(),
            "memory": self.memory(),
            "disk": self.disk(),
            "battery": self.battery(),
            "metrics_available": self.metrics_available(),
        }

    def summary(self) -> str:
        """Short human/speech-friendly summary. Never raises."""
        try:
            data = self.details()
        except Exception as error:  # defensive: summary must always answer
            log.warning("system info failed: %r", error)
            return "System information is unavailable right now."

        host = data["platform"]
        parts = [
            f"{host['system']} {host['release']} on {host['machine']}",
            f"{data['cpu']['cores']} CPU cores",
        ]
        percent = data["cpu"].get("percent")
        if percent is not None:
            parts.append(f"CPU at {percent:.0f}%")
        memory = data["memory"]
        if memory.get("available"):
            parts.append(
                f"RAM {memory['used_percent']:.0f}% of {memory['total_gb']} GB used"
            )
        else:
            parts.append("memory metrics unavailable (psutil not installed)")
        disk = data["disk"]
        if "free_gb" in disk:
            parts.append(f"{disk['free_gb']} GB free on {disk['path']}")
        battery = data["battery"]
        if battery.get("available"):
            plug = "charging" if battery["plugged"] else "on battery"
            parts.append(f"battery {battery['percent']:.0f}% ({plug})")
        return ", ".join(parts) + "."

    # Legacy aliases kept so older callers keep working.
    report = summary
    info = details


system_info = SystemInfo()


def summary() -> str:
    """Module-level mirror of :meth:`SystemInfo.summary`."""
    return system_info.summary()


def details() -> Dict[str, Any]:
    """Module-level mirror of :meth:`SystemInfo.details`."""
    return system_info.details()


def metrics_available() -> bool:
    """Module-level mirror of :meth:`SystemInfo.metrics_available`."""
    return system_info.metrics_available()


def report() -> str:
    """Legacy alias for :func:`summary`."""
    return summary()


def info() -> Dict[str, Any]:
    """Legacy alias for :func:`details`."""
    return details()
