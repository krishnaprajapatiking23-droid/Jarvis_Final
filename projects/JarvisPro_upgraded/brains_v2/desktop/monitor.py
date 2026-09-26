"""Desktop monitor information (roadmap section 30)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional

__all__ = ["monitors", "primary", "status"]

TIMEOUT = 4.0


def _run(command: List[str]) -> str:
    if not shutil.which(command[0]):
        return ""
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def monitors() -> List[Dict[str, Any]]:
    """Connected displays, best effort per platform."""
    found: List[Dict[str, Any]] = []

    try:
        from screeninfo import get_monitors  # type: ignore

        for index, screen in enumerate(get_monitors()):
            found.append({"index": index, "name": getattr(screen, "name", ""),
                          "width": screen.width, "height": screen.height,
                          "primary": bool(getattr(screen, "is_primary", index == 0))})
        if found:
            return found
    except Exception:
        pass

    if platform.system() == "Linux" and os.environ.get("DISPLAY"):
        for line in _run(["xrandr", "--query"]).splitlines():
            if " connected" not in line:
                continue
            parts = line.split()
            size = next((p for p in parts if "x" in p and p[0].isdigit()), "")
            width, _, height = size.partition("x")
            height = height.split("+")[0]
            found.append({
                "index": len(found), "name": parts[0],
                "width": int(width) if width.isdigit() else 0,
                "height": int(height) if height.isdigit() else 0,
                "primary": "primary" in line,
            })

    return found


def primary() -> Optional[Dict[str, Any]]:
    screens = monitors()
    if not screens:
        return None
    return next((s for s in screens if s.get("primary")), screens[0])


def status() -> Dict[str, Any]:
    screens = monitors()
    if not screens:
        return {"available": False, "monitors": [],
                "detail": "no display information available (headless?)"}
    return {"available": True, "monitors": screens,
            "detail": "%d display(s)" % len(screens)}
