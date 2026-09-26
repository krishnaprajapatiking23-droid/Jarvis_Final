"""Network reachability checks (roadmap section 31).

Pure standard library: a TCP connect with a timeout. No pings, no shell.
"""

from __future__ import annotations

import socket
import time
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["reachable", "online", "local_ip", "free_port", "probe", "status"]

PROBE_TARGETS: Tuple[Tuple[str, int], ...] = (
    ("1.1.1.1", 53), ("8.8.8.8", 53), ("9.9.9.9", 53),
)
DEFAULT_TIMEOUT = 2.0


def reachable(host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def online(timeout: float = DEFAULT_TIMEOUT) -> bool:
    return any(reachable(host, port, timeout) for host, port in PROBE_TARGETS)


def local_ip() -> str:
    """Best-effort LAN address without sending a packet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def free_port(preferred: Optional[int] = None) -> int:
    """A port that is free right now; the preferred one when possible."""
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("", int(preferred)))
                return int(preferred)
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def probe(host: str, ports: List[int],
          timeout: float = DEFAULT_TIMEOUT) -> Dict[int, bool]:
    return {port: reachable(host, port, timeout) for port in ports}


def status() -> Dict[str, Any]:
    started = time.time()
    connected = online()
    return {
        "online": connected,
        "local_ip": local_ip(),
        "hostname": socket.gethostname(),
        "checked_in_ms": round((time.time() - started) * 1000, 1),
    }
