"""Bluetooth status (roadmap section 34).

Reports what the platform can tell us. Honest about the common case: without
a bluetooth stack installed it says so instead of returning an empty list that
looks like "no devices".
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any, Dict, List

__all__ = ["supported", "devices", "status"]

TIMEOUT = 5.0


def _run(command: List[str]) -> str:
    if not shutil.which(command[0]):
        return ""
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def supported() -> bool:
    system = platform.system()
    if system == "Linux":
        return bool(shutil.which("bluetoothctl"))
    if system == "Darwin":
        return bool(shutil.which("system_profiler"))
    if system == "Windows":
        return True
    return False


def devices() -> List[Dict[str, str]]:
    if platform.system() != "Linux":
        return []
    found: List[Dict[str, str]] = []
    for line in _run(["bluetoothctl", "devices"]).splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            found.append({"address": parts[1], "name": parts[2]})
    return found


def status() -> Dict[str, Any]:
    if not supported():
        return {"available": False, "devices": [],
                "detail": "no bluetooth tooling found on this system"}
    paired = devices()
    return {"available": True, "devices": paired,
            "detail": "%d paired device(s)" % len(paired)}
