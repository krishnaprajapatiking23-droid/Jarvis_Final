"""Optional local-network discovery for the Android companion (Phase 7).

The PC answers a small UDP probe with its host, port and TLS flag, so the
phone can offer a list of reachable Jarvis servers. Discovery is strictly
optional: manual host/port entry always remains available, and no network
range is ever assumed.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Any, Dict, Optional

__all__ = [
    "DISCOVERY_PORT",
    "PROBE",
    "SERVICE",
    "advertisement",
    "local_ip",
    "DiscoveryAdvertiser",
]

log = logging.getLogger(__name__)

DISCOVERY_PORT = 8766
PROBE = b"JARVIS_DISCOVER_V1"
SERVICE = "jarvis"


def local_ip() -> str:
    """Best-effort primary LAN address, without assuming a subnet."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("203.0.113.1", 9))  # RFC 5737 test net; no traffic sent
        return str(probe.getsockname()[0])
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        probe.close()


def advertisement(
    name: str = "Jarvis",
    port: int = 8765,
    tls: bool = False,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the payload returned to a discovering client."""
    return {
        "service": SERVICE,
        "name": str(name),
        "host": host or local_ip(),
        "port": int(port),
        "tls": bool(tls),
        "version": 1,
    }


class DiscoveryAdvertiser:
    """Answers UDP discovery probes on the local network."""

    def __init__(
        self,
        name: str = "Jarvis",
        port: int = 8765,
        listen_port: int = DISCOVERY_PORT,
        tls: bool = False,
    ) -> None:
        self.name = str(name)
        self.port = int(port)
        self.listen_port = int(listen_port)
        self.tls = bool(tls)
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def payload(self) -> Dict[str, Any]:
        return advertisement(self.name, self.port, self.tls)

    def _serve(self) -> None:
        """Reply to probes until stopped. Timeout keeps the loop cancellable."""
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                data, sender = self._socket.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.strip() != PROBE:
                log.debug("ignoring unknown discovery payload from %s", sender)
                continue
            try:
                self._socket.sendto(
                    json.dumps(self.payload()).encode("utf-8"), sender
                )
            except OSError as error:
                log.debug("discovery reply failed: %r", error)

    def start(self) -> bool:
        """Begin advertising. Returns False when the port is unavailable."""
        if self.running:
            return True
        self._stop.clear()
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("", self.listen_port))
            server.settimeout(0.5)
        except OSError as error:
            log.warning("discovery could not bind udp/%d: %r", self.listen_port, error)
            return False
        self._socket = server
        self._thread = threading.Thread(
            target=self._serve, name="jarvis-discovery", daemon=True
        )
        self._thread.start()
        log.info("discovery advertising on udp/%d", self.listen_port)
        return True

    def stop(self, timeout: float = 2.0) -> None:
        """Stop advertising and join the worker thread (no leaks)."""
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
