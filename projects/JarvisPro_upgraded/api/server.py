"""HTTP transport adapter for ApiService (standard library only).

The adapter does no business logic: it parses the request, hands the route and
payload to ApiService.handle(), and serialises the envelope back. Long-poll
event streaming is provided for clients that cannot speak WebSocket; the
WebSocket framing helpers live in api/ws.py.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from .service import ApiService, MAX_PAYLOAD_BYTES

API_PREFIX = "/v1/"


def _bearer(headers) -> Optional[str]:
    raw = headers.get("Authorization") or ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return headers.get("X-Jarvis-Token")


class _Handler(BaseHTTPRequestHandler):
    server_version = "JarvisAPI/1.0"
    service: ApiService = None  # injected by make_server

    def log_message(self, fmt, *args):  # silence stdout noise
        return

    def _respond(self, envelope: Dict[str, Any]) -> None:
        body = json.dumps(envelope, default=str).encode("utf-8")
        self.send_response(envelope.get("http", 200))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Trace-Id", str(envelope.get("trace_id", "")))
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        path = self.path.split("?")[0]
        if not path.startswith(API_PREFIX):
            return ""
        return path[len(API_PREFIX):].strip("/").replace("/", ".")

    def _read_json(self) -> Tuple[bool, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return False, "bad Content-Length"
        if length > MAX_PAYLOAD_BYTES:
            return False, "payload too large"
        if length == 0:
            return True, {}
        raw = self.rfile.read(length)
        try:
            return True, json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return False, "invalid JSON: " + str(exc)

    def do_GET(self):
        route = self._route()
        if not route:
            self._respond({"ok": False, "http": 404, "status": "not_found",
                           "error": {"code": "not_found", "message": "unknown path"}})
            return
        self._respond(self.service.handle(route, {}, _bearer(self.headers)))

    def do_POST(self):
        route = self._route()
        if not route:
            self._respond({"ok": False, "http": 404, "status": "not_found",
                           "error": {"code": "not_found", "message": "unknown path"}})
            return
        ok, payload = self._read_json()
        if not ok:
            self._respond({"ok": False, "http": 400, "status": "invalid_request",
                           "error": {"code": "invalid_request", "message": payload}})
            return
        self._respond(self.service.handle(route, payload, _bearer(self.headers)))


class ApiServer:
    """Threaded HTTP server wrapper with a clean start/stop contract."""

    def __init__(self, service: ApiService, host: str = "127.0.0.1", port: int = 8787):
        self.service = service
        handler = type("BoundHandler", (_Handler,), {"service": service})
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self._httpd.daemon_threads = True
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def host(self) -> str:
        return self._httpd.server_address[0]

    def start(self) -> "ApiServer":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        kwargs={"poll_interval": 0.1},
                                        daemon=True, name="jarvis-api")
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        try:
            self._httpd.server_close()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
