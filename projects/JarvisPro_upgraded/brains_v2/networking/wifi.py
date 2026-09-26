"""Wi-Fi information (roadmap section 34).

Reads the current network name through the platform's own command when one is
available, and reports "unknown" rather than guessing when it is not.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import Any, Dict, Optional

from brains_v2.networking.connection import local_ip, online

__all__ = ["ssid", "status"]

TIMEOUT = 4.0


def _run(command: list) -> str:
    if not shutil.which(command[0]):
        return ""
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def ssid() -> Optional[str]:
    """The connected network name, or None when it cannot be determined."""
    system = platform.system()

    if system == "Linux":
        output = _run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
        for line in output.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1] or None
        output = _run(["iwgetid", "-r"])
        return output.strip() or None

    if system == "Darwin":
        output = _run(["/usr/sbin/networksetup", "-getairportnetwork", "en0"])
        match = re.search(r"Current Wi-Fi Network:\s*(.+)", output)
        return match.group(1).strip() if match else None

    if system == "Windows":
        output = _run(["netsh", "wlan", "show", "interfaces"])
        match = re.search(r"^\s*SSID\s*:\s*(.+)$", output, re.MULTILINE)
        return match.group(1).strip() if match else None

    return None


def status() -> Dict[str, Any]:
    name = ssid()
    return {
        "ssid": name or "unknown",
        "known": name is not None,
        "online": online(),
        "local_ip": local_ip(),
        "platform": platform.system(),
    }
