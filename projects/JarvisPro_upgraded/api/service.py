"""Jarvis API service layer.

Transport-agnostic. This module owns authentication, authorization, request
validation, rate limiting, tracing, error envelopes and the event bus that
WebSocket / HTTP adapters expose. It contains NO business logic: every route
delegates to an existing Jarvis service (kernel.tasks, kernel.memory,
kernel.policy, kernel.resources, kernel.managers...).

If a backing service is absent the route answers UNAVAILABLE instead of
crashing or faking a result.
"""

import hashlib
import hmac
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

OK = "ok"
UNAVAILABLE = "UNAVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"

ROLE_RANK = {"device": 1, "user": 2, "admin": 3}

PBKDF_ROUNDS = 120000
DEFAULT_RATE_LIMIT = 60
DEFAULT_RATE_WINDOW = 60.0
MAX_PAYLOAD_BYTES = 256 * 1024
EVENT_QUEUE_SIZE = 256


def _now() -> float:
    return time.time()


def new_trace_id() -> str:
    return "api-" + uuid.uuid4().hex[:16]


class ApiError(Exception):
    def __init__(self, status: str, message: str, http: int = 400):
        super().__init__(message)
        self.status = status
        self.message = message
        self.http = http


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

TYPES = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "dict": dict,
    "list": list,
}


def validate(payload: Any, schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a request payload against a tiny declarative schema.

    schema: {field: {"type": "str", "required": True, "max": 500}}
    Unknown fields are rejected so typos surface instead of being ignored.
    """
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "payload must be an object", 400)
    unknown = sorted(set(payload) - set(schema))
    if unknown:
        raise ApiError("invalid_request", "unknown fields: " + ", ".join(unknown), 400)
    clean: Dict[str, Any] = {}
    for field, rule in schema.items():
        present = field in payload and payload[field] is not None
        if not present:
            if rule.get("required"):
                raise ApiError("invalid_request", "missing field: " + field, 400)
            if "default" in rule:
                clean[field] = rule["default"]
            continue
        value = payload[field]
        expected = TYPES[rule.get("type", "str")]
        if rule.get("type") in ("int", "float") and isinstance(value, bool):
            raise ApiError("invalid_request", field + " must be " + rule["type"], 400)
        if not isinstance(value, expected):
            raise ApiError("invalid_request", field + " must be " + rule.get("type", "str"), 400)
        if isinstance(value, str):
            if not value.strip() and rule.get("required"):
                raise ApiError("invalid_request", field + " must not be empty", 400)
            limit = rule.get("max", 4000)
            if len(value) > limit:
                raise ApiError("invalid_request", field + " exceeds " + str(limit) + " chars", 400)
        clean[field] = value
    return clean


# --------------------------------------------------------------------------
# rate limiting
# --------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window limiter, per principal. Thread safe."""

    def __init__(self, limit: int = DEFAULT_RATE_LIMIT, window: float = DEFAULT_RATE_WINDOW):
        self.limit = limit
        self.window = window
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, principal: str, now: Optional[float] = None) -> Tuple[bool, int]:
        now = _now() if now is None else now
        with self._lock:
            hits = [t for t in self._hits.get(principal, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[principal] = hits
                return False, 0
            hits.append(now)
            self._hits[principal] = hits
            return True, self.limit - len(hits)

    def reset(self, principal: Optional[str] = None) -> None:
        with self._lock:
            if principal is None:
                self._hits.clear()
            else:
                self._hits.pop(principal, None)


# --------------------------------------------------------------------------
# events (backs WebSocket / long poll)
# --------------------------------------------------------------------------


class Subscription:
    def __init__(self, bus: "EventBus", principal: str):
        self.bus = bus
        self.principal = principal
        self.queue: "queue.Queue" = queue.Queue(maxsize=EVENT_QUEUE_SIZE)
        self.dropped = 0
        self.closed = False

    def deliver(self, event: Dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            try:
                self.queue.put_nowait(event)
            except queue.Full:
                pass

    def poll(self, max_items: int = 50, timeout: float = 0.0) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        deadline = _now() + timeout
        while len(out) < max_items:
            try:
                remaining = deadline - _now()
                if out or remaining <= 0:
                    out.append(self.queue.get_nowait())
                else:
                    out.append(self.queue.get(timeout=remaining))
            except queue.Empty:
                break
        return out

    def close(self) -> None:
        self.closed = True
        self.bus.unsubscribe(self)


class EventBus:
    def __init__(self) -> None:
        self._subs: List[Subscription] = []
        self._lock = threading.Lock()

    def subscribe(self, principal: str) -> Subscription:
        sub = Subscription(self, principal)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def publish(self, kind: str, payload: Dict[str, Any], principal: Optional[str] = None) -> int:
        event = {"kind": kind, "at": _now(), "payload": payload}
        sent = 0
        with self._lock:
            targets = list(self._subs)
        for sub in targets:
            if principal and sub.principal != principal:
                continue
            sub.deliver(dict(event))
            sent += 1
        return sent

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)


# --------------------------------------------------------------------------
# service
# --------------------------------------------------------------------------


class ApiService:
    capability = "api"

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None,
                 rate_limit: int = DEFAULT_RATE_LIMIT,
                 rate_window: float = DEFAULT_RATE_WINDOW,
                 command_handler: Optional[Callable[[str, str], Any]] = None):
        self.kernel = kernel
        self.db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()
        self.limiter = RateLimiter(rate_limit, rate_window)
        self.events = EventBus()
        self._command_handler = command_handler
        self.routes: Dict[str, Dict[str, Any]] = self._build_routes()

    # -- storage ---------------------------------------------------------
    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS api_tokens (token_id TEXT PRIMARY KEY, principal TEXT,"
                " role TEXT, salt TEXT, secret_hash TEXT, created REAL, expires REAL, revoked INTEGER DEFAULT 0)")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS api_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL,"
                " trace_id TEXT, principal TEXT, route TEXT, status TEXT, duration_ms REAL, error TEXT)")

    # -- authentication --------------------------------------------------
    def issue_token(self, principal: str, role: str = "user",
                    ttl_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Create a token. The plaintext secret is returned ONCE and never stored."""
        if role not in ROLE_RANK:
            raise ApiError("invalid_request", "unknown role: " + str(role), 400)
        token_id = uuid.uuid4().hex[:12]
        secret = uuid.uuid4().hex + uuid.uuid4().hex
        salt = os.urandom(16).hex()
        digest = self._hash(secret, salt)
        created = _now()
        expires = created + ttl_seconds if ttl_seconds else None
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO api_tokens (token_id, principal, role, salt, secret_hash, created, expires)"
                " VALUES (?,?,?,?,?,?,?)",
                (token_id, principal, role, salt, digest, created, expires))
        return {"token": token_id + "." + secret, "token_id": token_id,
                "principal": principal, "role": role, "expires": expires}

    @staticmethod
    def _hash(secret: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), PBKDF_ROUNDS).hex()

    def verify_token(self, token: Optional[str]) -> Dict[str, Any]:
        if not token or not isinstance(token, str) or "." not in token:
            raise ApiError("unauthenticated", "missing or malformed token", 401)
        token_id, _, secret = token.partition(".")
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_tokens WHERE token_id = ?", (token_id,)).fetchone()
        if row is None:
            raise ApiError("unauthenticated", "unknown token", 401)
        if row["revoked"]:
            raise ApiError("unauthenticated", "token revoked", 401)
        if row["expires"] and _now() > row["expires"]:
            raise ApiError("unauthenticated", "token expired", 401)
        if not hmac.compare_digest(self._hash(secret, row["salt"]), row["secret_hash"]):
            raise ApiError("unauthenticated", "bad token secret", 401)
        return {"principal": row["principal"], "role": row["role"], "token_id": token_id}

    def revoke_token(self, token_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE api_tokens SET revoked = 1 WHERE token_id = ?", (token_id,))
        return cur.rowcount > 0

    def list_tokens(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT token_id, principal, role, created, expires, revoked FROM api_tokens").fetchall()
        return [dict(r) for r in rows]

    # -- routing ---------------------------------------------------------
    def _build_routes(self) -> Dict[str, Dict[str, Any]]:
        return {
            "health": {"role": None, "schema": {}, "handler": self._h_health},
            "auth.whoami": {"role": "device", "schema": {}, "handler": self._h_whoami},
            "command.execute": {
                "role": "user", "policy": "api.command",
                "schema": {"text": {"type": "str", "required": True, "max": 2000},
                           "source": {"type": "str", "default": "api"}},
                "handler": self._h_command},
            "task.create": {
                "role": "user", "policy": "api.task.write",
                "schema": {"title": {"type": "str", "required": True, "max": 500}},
                "handler": self._h_task_create},
            "task.status": {
                "role": "device",
                "schema": {"task_id": {"type": "str", "required": True}},
                "handler": self._h_task_status},
            "task.list": {"role": "device", "schema": {}, "handler": self._h_task_list},
            "task.cancel": {
                "role": "user", "policy": "api.task.write",
                "schema": {"task_id": {"type": "str", "required": True},
                           "reason": {"type": "str", "default": "cancelled via API"}},
                "handler": self._h_task_cancel},
            "memory.search": {
                "role": "user",
                "schema": {"query": {"type": "str", "required": True, "max": 500},
                           "limit": {"type": "int", "default": 10}},
                "handler": self._h_memory_search},
            "system.status": {"role": "device", "schema": {}, "handler": self._h_system_status},
            "notification.send": {
                "role": "user",
                "schema": {"title": {"type": "str", "required": True, "max": 200},
                           "body": {"type": "str", "default": ""},
                           "level": {"type": "str", "default": "info"}},
                "handler": self._h_notify},
            "event.poll": {
                "role": "device",
                "schema": {"timeout": {"type": "float", "default": 0.0},
                           "max_items": {"type": "int", "default": 50}},
                "handler": self._h_event_poll},
            "admin.tokens": {"role": "admin", "schema": {}, "handler": self._h_admin_tokens},
        }

    def handle(self, route: str, payload: Any = None, token: Optional[str] = None,
               trace_id: Optional[str] = None, subscription: Optional[Subscription] = None) -> Dict[str, Any]:
        """Single entry point for every transport. Never raises."""
        started = _now()
        trace_id = trace_id or self._new_trace(route)
        principal = "anonymous"
        try:
            spec = self.routes.get(route)
            if spec is None:
                raise ApiError("not_found", "unknown route: " + str(route), 404)
            raw = payload if payload is not None else {}
            if len(json.dumps(raw, default=str)) > MAX_PAYLOAD_BYTES:
                raise ApiError("invalid_request", "payload too large", 413)
            identity = {"principal": "anonymous", "role": "device"}
            if spec["role"] is not None:
                identity = self.verify_token(token)
                if ROLE_RANK[identity["role"]] < ROLE_RANK[spec["role"]]:
                    raise ApiError("forbidden", "role " + identity["role"] + " may not call " + route, 403)
            principal = identity["principal"]
            if spec["role"] is not None:
                allowed, remaining = self.limiter.check(principal)
                if not allowed:
                    raise ApiError("rate_limited", "rate limit exceeded", 429)
            args = validate(raw, spec["schema"])
            if spec.get("policy"):
                self._policy_check(spec["policy"], identity, trace_id)
            data = spec["handler"](args, identity, trace_id, subscription)
            envelope = self._ok(route, data, trace_id, started, principal)
            return envelope
        except ApiError as exc:
            return self._err(route, exc, trace_id, started, principal)
        except Exception as exc:  # unexpected: never leak a stack trace to a client
            return self._err(route, ApiError("internal_error", type(exc).__name__ + ": " + str(exc), 500),
                             trace_id, started, principal)

    # -- policy ----------------------------------------------------------
    def _policy_check(self, scope: str, identity: Dict[str, Any], trace_id: str) -> None:
        policy = getattr(self.kernel, "policy", None)
        if policy is None:
            return
        check = getattr(policy, "check", None)
        if check is None:
            return
        try:
            verdict = check(scope, subject=identity["principal"])
        except TypeError:
            try:
                verdict = check(scope)
            except Exception as exc:
                raise ApiError("forbidden", "policy error: " + str(exc), 403)
        except Exception as exc:
            raise ApiError("forbidden", "policy error: " + str(exc), 403)
        allowed = verdict
        if isinstance(verdict, dict):
            allowed = verdict.get("allowed", verdict.get("granted", False))
        if not allowed:
            raise ApiError("permission_required", "policy denied scope " + scope, 403)

    # -- handlers (delegate only) ----------------------------------------
    def _service(self, name: str) -> Any:
        svc = getattr(self.kernel, name, None)
        if svc is None:
            raise ApiError(UNAVAILABLE, name + " service is not available", 503)
        return svc

    def _h_health(self, args, identity, trace_id, sub):
        managers: Dict[str, Any] = {}
        registry = getattr(self.kernel, "managers", None)
        if registry is not None and hasattr(registry, "health"):
            try:
                managers = registry.health()
            except Exception as exc:
                managers = {"error": str(exc)}
        return {"status": OK, "kernel": self.kernel is not None,
                "subscribers": self.events.subscriber_count, "managers": managers}

    def _h_whoami(self, args, identity, trace_id, sub):
        return dict(identity)

    def _h_command(self, args, identity, trace_id, sub):
        handler = self._command_handler
        if handler is None:
            for attr in ("handle_command", "handle", "process"):
                candidate = getattr(self.kernel, attr, None)
                if callable(candidate):
                    handler = lambda text, src, _c=candidate: _c(text)
                    break
        if handler is None:
            raise ApiError(UNAVAILABLE, "no command pipeline is wired into the kernel", 503)
        result = handler(args["text"], args.get("source", "api"))
        self.events.publish("command.completed", {"text": args["text"], "trace_id": trace_id})
        return {"result": result}

    def _h_task_create(self, args, identity, trace_id, sub):
        task = self._service("tasks").create(args["title"])
        data = task.to_dict() if hasattr(task, "to_dict") else {"task": str(task)}
        self.events.publish("task.created", data)
        return data

    def _h_task_status(self, args, identity, trace_id, sub):
        tasks = self._service("tasks")
        try:
            task = tasks.get(args["task_id"])
        except Exception:
            raise ApiError("not_found", "no such task: " + args["task_id"], 404)
        return task.to_dict() if hasattr(task, "to_dict") else {"task": str(task)}

    def _h_task_list(self, args, identity, trace_id, sub):
        tasks = self._service("tasks")
        summary = tasks.summary() if hasattr(tasks, "summary") else {}
        return {"summary": summary}

    def _h_task_cancel(self, args, identity, trace_id, sub):
        tasks = self._service("tasks")
        try:
            result = tasks.cancel(args["task_id"], args.get("reason", ""))
        except Exception as exc:
            raise ApiError("not_found", str(exc), 404)
        self.events.publish("task.cancelled", {"task_id": args["task_id"]})
        return result if isinstance(result, dict) else {"cancelled": bool(result)}

    def _h_memory_search(self, args, identity, trace_id, sub):
        memory = self._service("memory")
        for attr in ("search", "recall", "query"):
            fn = getattr(memory, attr, None)
            if callable(fn):
                try:
                    hits = fn(args["query"], args.get("limit", 10))
                except TypeError:
                    hits = fn(args["query"])
                return {"results": list(hits) if hits else []}
        raise ApiError(UNAVAILABLE, "memory service exposes no search interface", 503)

    def _h_system_status(self, args, identity, trace_id, sub):
        out: Dict[str, Any] = {"api": OK}
        resources = getattr(self.kernel, "resources", None)
        if resources is None:
            out["resources"] = UNAVAILABLE
        else:
            for attr in ("snapshot", "status", "sample"):
                fn = getattr(resources, attr, None)
                if callable(fn):
                    try:
                        out["resources"] = fn()
                    except Exception as exc:
                        out["resources"] = {"status": UNAVAILABLE, "error": str(exc)}
                    break
            else:
                out["resources"] = UNAVAILABLE
        return out

    def _h_notify(self, args, identity, trace_id, sub):
        payload = {"title": args["title"], "body": args.get("body", ""),
                   "level": args.get("level", "info"), "trace_id": trace_id}
        delivered = self.events.publish("notification", payload)
        return {"delivered_to": delivered, "notification": payload}

    def _h_event_poll(self, args, identity, trace_id, sub):
        if sub is None:
            raise ApiError("invalid_request", "event.poll requires a subscription", 400)
        events = sub.poll(int(args.get("max_items", 50)), float(args.get("timeout", 0.0)))
        return {"events": events, "dropped": sub.dropped}

    def _h_admin_tokens(self, args, identity, trace_id, sub):
        return {"tokens": self.list_tokens()}

    # -- envelopes + audit -----------------------------------------------
    def _new_trace(self, route: str) -> str:
        obs = getattr(self.kernel, "observability", None)
        if obs is not None and hasattr(obs, "new_trace_id"):
            try:
                return obs.new_trace_id()
            except Exception:
                pass
        return new_trace_id()

    def _ok(self, route, data, trace_id, started, principal):
        duration = (_now() - started) * 1000.0
        self._audit(trace_id, principal, route, OK, duration, None)
        return {"ok": True, "status": OK, "http": 200, "route": route,
                "data": data, "trace_id": trace_id, "duration_ms": round(duration, 3)}

    def _err(self, route, exc: ApiError, trace_id, started, principal):
        duration = (_now() - started) * 1000.0
        self._audit(trace_id, principal, route, exc.status, duration, exc.message)
        return {"ok": False, "status": exc.status, "http": exc.http, "route": route,
                "error": {"code": exc.status, "message": exc.message},
                "trace_id": trace_id, "duration_ms": round(duration, 3)}

    def _audit(self, trace_id, principal, route, status, duration, error) -> None:
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO api_requests (at, trace_id, principal, route, status, duration_ms, error)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (_now(), trace_id, principal, route, status, duration, error))
        except Exception:
            pass
        analytics = getattr(self.kernel, "analytics", None)
        if analytics is not None and hasattr(analytics, "record"):
            try:
                analytics.record("tool", "api." + route, success=(status == OK),
                                 duration_ms=duration, trace_id=trace_id)
            except Exception:
                pass

    def audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM api_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- manager contract -------------------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM api_requests").fetchone()["c"]
            failed = self._conn.execute(
                "SELECT COUNT(*) c FROM api_requests WHERE status != ?", (OK,)).fetchone()["c"]
            tokens = self._conn.execute(
                "SELECT COUNT(*) c FROM api_tokens WHERE revoked = 0").fetchone()["c"]
        return {"manager": "api", "requests": total, "failed": failed,
                "active_tokens": tokens, "subscribers": self.events.subscriber_count}

    def health(self) -> Dict[str, Any]:
        info = self.status()
        info["available"] = True
        return info

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
