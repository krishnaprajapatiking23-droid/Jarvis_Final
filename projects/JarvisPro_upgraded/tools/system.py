"""System information tool.

Reports CPU, memory, disk, uptime and platform. Uses psutil when available
and falls back to the standard library so it never hard-fails.
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from typing import Any, Dict

try:
    import psutil
except Exception:
    psutil = None

__all__ = ["SystemTool", "system_tool", "snapshot"]

_START = time.time()


class SystemTool:
    """Live machine telemetry."""

    name = "system"
    description = "CPU, memory, disk and platform information."

    def cpu(self) -> Dict[str, Any]:
        if psutil is not None:
            return {
                "percent": psutil.cpu_percent(interval=0.1),
                "cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False),
            }
        return {"percent": None, "cores": os.cpu_count(),
                "physical_cores": None, "detail": "psutil not installed"}

    def memory(self) -> Dict[str, Any]:
        if psutil is not None:
            virtual = psutil.virtual_memory()
            return {
                "total_gb": round(virtual.total / 1e9, 2),
                "available_gb": round(virtual.available / 1e9, 2),
                "used_percent": virtual.percent,
            }
        return {"detail": "psutil not installed"}

    def disk(self, path: str = ".") -> Dict[str, Any]:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / 1e9, 2),
            "free_gb": round(usage.free / 1e9, 2),
            "used_percent": round(usage.used * 100.0 / usage.total, 1),
        }

    def platform(self) -> Dict[str, Any]:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "hostname": platform.node(),
        }

    def uptime_seconds(self) -> float:
        if psutil is not None:
            try:
                return round(time.time() - psutil.boot_time(), 1)
            except Exception:
                pass
        return round(time.time() - _START, 1)

    def report(self) -> Dict[str, Any]:
        return {
            "platform": self.platform(),
            "cpu": self.cpu(),
            "memory": self.memory(),
            "disk": self.disk(),
            "uptime_seconds": self.uptime_seconds(),
        }

    def summary(self) -> str:
        data = self.report()
        parts = ["%s %s on %s" % (data["platform"]["system"],
                                  data["platform"]["release"],
                                  data["platform"]["machine"])]
        if data["cpu"].get("percent") is not None:
            parts.append("CPU %.0f%% across %s cores"
                         % (data["cpu"]["percent"], data["cpu"]["cores"]))
        if "used_percent" in data["memory"]:
            parts.append("RAM %.0f%% of %sGB used"
                         % (data["memory"]["used_percent"],
                            data["memory"]["total_gb"]))
        parts.append("disk %.0f%% used, %sGB free"
                     % (data["disk"]["used_percent"], data["disk"]["free_gb"]))
        return ", ".join(parts) + "."


system_tool = SystemTool()


def snapshot() -> Dict[str, Any]:
    return system_tool.report()
