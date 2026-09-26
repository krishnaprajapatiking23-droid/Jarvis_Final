"""Batch 3g: API layer (api/) + task/ consolidation.

Run: python tests/test_subsystems_batch3g.py
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import ApiError, ApiService, RateLimiter, validate  # noqa: E402
from api import ws  # noqa: E402
from api.server import ApiServer  # noqa: E402
from jarvis_core.tasks import TaskManager, TaskStore  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("PASS " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + " -- " + str(detail))


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------


class DenyPolicy:
    def check(self, scope, subject=None):
        return {"allowed": False, "scope": scope}


class AllowPolicy:
    def __init__(self):
        self.seen = []

    def check(self, scope, subject=None):
        self.seen.append((scope, subject))
        return {"allowed": True}


class BrokenPolicy:
    def check(self, scope, subject=None):
        raise RuntimeError("policy backend down")


class RecordingAnalytics:
    def __init__(self):
        self.rows = []

    def record(self, kind, name, success=True, duration_ms=0.0, trace_id=None, **kw):
        self.rows.append((kind, name, success, trace_id))


class FakeMemory:
    def search(self, query, limit=10):
        return [{"text": "remembered: " + query}][:limit]


class FakeResources:
    def snapshot(self):
        return {"cpu": 12.5, "ram": 44.0}


class FakeRegistry:
    def health(self):
        return {"tasks": {"available": True}}


class FakeKernel:
    def __init__(self, policy=None, with_tasks=True, with_memory=True, command=None):
        self.policy = policy
        self.analytics = RecordingAnalytics()
        self.managers = FakeRegistry()
        self.resources = FakeResources()
        if with_tasks:
            self.tasks = TaskManager(TaskStore(None))
        if with_memory:
            self.memory = FakeMemory()
        if command is not None:
            self.handle_command = command


def make(policy=None, **kw):
    kernel = FakeKernel(policy=policy, **kw)
    svc = ApiService(None, kernel=kernel, rate_limit=1000)
    admin = svc.issue_token("krishna", "admin")["token"]
    user = svc.issue_token("desktop", "user")["token"]
    device = svc.issue_token("phone", "device")["token"]
    return svc, kernel, admin, user, device


# --------------------------------------------------------------------------
# 1. validation
# --------------------------------------------------------------------------

def test_validation():
    schema = {"text": {"type": "str", "required": True, "max": 10},
              "n": {"type": "int", "default": 5}}
    out = validate({"text": "hi"}, schema)
    check("validation applies defaults", out == {"text": "hi", "n": 5}, out)

    for bad, label in [({}, "missing required"),
                       ({"text": ""}, "empty required string"),
                       ({"text": "x" * 11}, "over max length"),
                       ({"text": "hi", "n": "five"}, "wrong type"),
                       ({"text": "hi", "n": True}, "bool is not int"),
                       ({"text": "hi", "zzz": 1}, "unknown field"),
                       ("a string", "non-object payload")]:
        try:
            validate(bad, schema)
            check("validation rejects " + label, False, "accepted " + repr(bad))
        except ApiError as exc:
            check("validation rejects " + label, exc.status == "invalid_request", exc.status)


# --------------------------------------------------------------------------
# 2. authentication
# --------------------------------------------------------------------------

def test_authentication():
    svc, _, admin, user, device = make()

    ident = svc.verify_token(user)
    check("valid token verifies", ident["principal"] == "desktop" and ident["role"] == "user", ident)

    rows = svc._conn.execute("SELECT secret_hash FROM api_tokens").fetchall()
    secret = user.split(".", 1)[1]
    check("secret is never stored in plaintext",
          all(secret not in r["secret_hash"] for r in rows))

    for bad, label in [(None, "missing token"), ("", "empty token"),
                       ("garbage", "malformed token"),
                       ("deadbeef." + "0" * 64, "unknown token id"),
                       (user.split(".")[0] + ".wrongsecret", "wrong secret")]:
        try:
            svc.verify_token(bad)
            check("auth rejects " + label, False, "accepted")
        except ApiError as exc:
            check("auth rejects " + label, exc.http == 401, exc.http)

    expiring = svc.issue_token("temp", "user", ttl_seconds=-1)["token"]
    try:
        svc.verify_token(expiring)
        check("auth rejects expired token", False, "accepted")
    except ApiError as exc:
        check("auth rejects expired token", "expired" in exc.message, exc.message)

    info = svc.issue_token("revokeme", "user")
    check("revoke returns True once", svc.revoke_token(info["token_id"]) is True)
    try:
        svc.verify_token(info["token"])
        check("auth rejects revoked token", False, "accepted")
    except ApiError as exc:
        check("auth rejects revoked token", "revoked" in exc.message, exc.message)

    try:
        svc.issue_token("x", "superuser")
        check("unknown role rejected", False, "accepted")
    except ApiError as exc:
        check("unknown role rejected", exc.status == "invalid_request", exc.status)
    svc.close()


# --------------------------------------------------------------------------
# 3. authorization
# --------------------------------------------------------------------------

def test_authorization():
    svc, _, admin, user, device = make()

    r = svc.handle("health", {}, None)
    check("health needs no token", r["ok"] and r["data"]["status"] == "ok", r)

    r = svc.handle("task.list", {}, None)
    check("protected route without token is 401", r["http"] == 401 and not r["ok"], r)

    r = svc.handle("command.execute", {"text": "hi"}, device)
    check("device role cannot run commands", r["http"] == 403 and r["status"] == "forbidden", r)

    r = svc.handle("admin.tokens", {}, user)
    check("user role cannot reach admin route", r["http"] == 403, r)

    r = svc.handle("admin.tokens", {}, admin)
    check("admin role reaches admin route", r["ok"] and len(r["data"]["tokens"]) >= 3, r)

    r = svc.handle("task.list", {}, device)
    check("device role reaches device route", r["ok"], r)

    r = svc.handle("auth.whoami", {}, user)
    check("whoami reports identity", r["data"]["principal"] == "desktop", r)
    svc.close()


# --------------------------------------------------------------------------
# 4. routing / delegation
# --------------------------------------------------------------------------

def test_routing():
    calls = []

    def command(text):
        calls.append(text)
        return {"spoken": "opening calculator"}

    svc, kernel, admin, user, device = make(policy=AllowPolicy(), command=command)

    r = svc.handle("command.execute", {"text": "open calculator"}, user)
    check("command delegates to kernel pipeline",
          r["ok"] and calls == ["open calculator"] and r["data"]["result"]["spoken"], r)

    r = svc.handle("task.create", {"title": "Study accounts"}, user)
    # jarvis_core.tasks.Task.to_dict() keys the identifier "task_id", not "id"
    task_id = r["data"].get("task_id")
    check("task.create uses jarvis_core.tasks", r["ok"] and bool(task_id), r)

    r2 = svc.handle("task.status", {"task_id": task_id}, device)
    check("task.status returns the real task",
          r2["ok"] and r2["data"]["title"] == "Study accounts", r2)

    r3 = svc.handle("task.status", {"task_id": "nope"}, device)
    check("unknown task is 404", r3["http"] == 404, r3)

    r4 = svc.handle("task.cancel", {"task_id": task_id}, user)
    check("task.cancel delegates", r4["ok"], r4)

    r5 = svc.handle("memory.search", {"query": "birthday"}, user)
    check("memory.search delegates", r5["ok"] and r5["data"]["results"], r5)

    r6 = svc.handle("system.status", {}, device)
    check("system.status reports live resources",
          r6["ok"] and r6["data"]["resources"]["cpu"] == 12.5, r6)

    r7 = svc.handle("does.not.exist", {}, user)
    check("unknown route is 404", r7["http"] == 404 and r7["status"] == "not_found", r7)
    svc.close()


# --------------------------------------------------------------------------
# 5. policy integration
# --------------------------------------------------------------------------

def test_policy():
    svc, kernel, admin, user, device = make(policy=DenyPolicy(), command=lambda t: "ran")
    r = svc.handle("command.execute", {"text": "delete everything"}, user)
    check("policy denial blocks the route",
          r["status"] == "permission_required" and r["http"] == 403, r)

    allow = AllowPolicy()
    svc2, _, _, user2, _ = make(policy=allow, command=lambda t: "ran")
    r2 = svc2.handle("command.execute", {"text": "open notes"}, user2)
    check("policy receives scope and subject",
          r2["ok"] and allow.seen and allow.seen[0][0] == "api.command", allow.seen)

    svc3, _, _, user3, _ = make(policy=BrokenPolicy(), command=lambda t: "ran")
    r3 = svc3.handle("command.execute", {"text": "open notes"}, user3)
    check("broken policy fails closed", not r3["ok"] and r3["http"] == 403, r3)
    for s in (svc, svc2, svc3):
        s.close()


# --------------------------------------------------------------------------
# 6. graceful degradation
# --------------------------------------------------------------------------

def test_unavailable():
    svc = ApiService(None, kernel=None)
    token = svc.issue_token("k", "admin")["token"]

    r = svc.handle("task.list", {}, token)
    check("missing task service reports UNAVAILABLE",
          r["status"] == "UNAVAILABLE" and r["http"] == 503, r)

    r2 = svc.handle("command.execute", {"text": "hi"}, token)
    check("missing command pipeline reports UNAVAILABLE", r2["status"] == "UNAVAILABLE", r2)

    r3 = svc.handle("health", {}, None)
    check("health still answers without a kernel",
          r3["ok"] and r3["data"]["kernel"] is False, r3)

    svc4, kernel, _, user, _ = make(with_memory=False)
    r4 = svc4.handle("memory.search", {"query": "x"}, user)
    check("missing memory reports UNAVAILABLE not crash", r4["status"] == "UNAVAILABLE", r4)

    class Exploding:
        def snapshot(self):
            raise RuntimeError("sensor gone")

    kernel.resources = Exploding()
    r5 = svc4.handle("system.status", {}, user)
    check("resource failure degrades instead of 500",
          r5["ok"] and r5["data"]["resources"]["status"] == "UNAVAILABLE", r5)
    svc.close()
    svc4.close()


# --------------------------------------------------------------------------
# 7. error handling / no leaked tracebacks
# --------------------------------------------------------------------------

def test_error_handling():
    def boom(text):
        raise ValueError("pipeline exploded")

    svc, _, _, user, _ = make(command=boom)
    r = svc.handle("command.execute", {"text": "go"}, user)
    check("unexpected error becomes a 500 envelope",
          not r["ok"] and r["http"] == 500 and r["status"] == "internal_error", r)
    check("error envelope carries no traceback",
          "Traceback" not in json.dumps(r), r)
    check("error envelope still has a trace id", r["trace_id"].startswith("api-"), r)

    r2 = svc.handle("command.execute", {"nope": 1}, user)
    check("invalid payload is 400", r2["http"] == 400, r2)

    big = {"text": "x" * 300000}
    r3 = svc.handle("command.execute", big, user)
    check("oversized payload is rejected", r3["http"] in (400, 413), r3)
    svc.close()


# --------------------------------------------------------------------------
# 8. rate limiting
# --------------------------------------------------------------------------

def test_rate_limit():
    limiter = RateLimiter(limit=2, window=10.0)
    ok1 = limiter.check("a")[0]
    ok2 = limiter.check("a")[0]
    ok3 = limiter.check("a")[0]
    check("limiter allows up to the limit then blocks", ok1 and ok2 and not ok3)
    check("limiter is per principal", limiter.check("b")[0] is True)

    now = time.time()
    limiter2 = RateLimiter(limit=1, window=5.0)
    limiter2.check("a", now=now)
    check("window slides", limiter2.check("a", now=now + 6)[0] is True)

    kernel = FakeKernel()
    svc = ApiService(None, kernel=kernel, rate_limit=2)
    token = svc.issue_token("k", "admin")["token"]
    svc.handle("task.list", {}, token)
    svc.handle("task.list", {}, token)
    r = svc.handle("task.list", {}, token)
    check("service returns 429 past the limit",
          r["http"] == 429 and r["status"] == "rate_limited", r)
    r2 = svc.handle("health", {}, None)
    check("health is not rate limited", r2["ok"], r2)
    svc.close()


# --------------------------------------------------------------------------
# 9. events / websocket transport
# --------------------------------------------------------------------------

def test_events():
    svc, _, _, user, device = make(command=lambda t: "ok")
    sub = svc.events.subscribe("desktop")

    svc.handle("notification.send", {"title": "Reminder", "body": "Drink water"}, user)
    events = sub.poll()
    check("notification reaches subscribers",
          len(events) == 1 and events[0]["kind"] == "notification", events)

    svc.handle("task.create", {"title": "t"}, user)
    r = svc.handle("event.poll", {}, device, subscription=sub)
    check("event.poll drains the queue",
          r["ok"] and r["data"]["events"][0]["kind"] == "task.created", r)

    r2 = svc.handle("event.poll", {}, device)
    check("event.poll without subscription is 400", r2["http"] == 400, r2)

    for i in range(300):
        svc.events.publish("spam", {"i": i})
    check("bounded queue drops oldest instead of growing",
          sub.dropped > 0 and sub.queue.qsize() <= 256, (sub.dropped, sub.queue.qsize()))

    sub.close()
    check("closed subscription is removed", svc.events.subscriber_count == 0)
    svc.close()


def test_websocket_framing():
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    check("handshake accept key matches RFC 6455",
          ws.accept_key(key) == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", ws.accept_key(key))

    resp = ws.handshake_response({"Upgrade": "websocket", "Sec-WebSocket-Key": key,
                                  "Sec-WebSocket-Version": "13"})
    check("handshake returns 101", resp.startswith("HTTP/1.1 101"), resp[:40])

    for headers, label in [({"Upgrade": "h2c"}, "non-websocket upgrade"),
                           ({"Upgrade": "websocket", "Sec-WebSocket-Version": "8",
                             "Sec-WebSocket-Key": key}, "old protocol version"),
                           ({"Upgrade": "websocket"}, "missing key")]:
        try:
            ws.handshake_response(headers)
            check("handshake rejects " + label, False, "accepted")
        except ws.WebSocketError:
            check("handshake rejects " + label, True)

    payload = json.dumps({"kind": "task.created"}).encode()
    for size, label in [(10, "small"), (500, "16-bit length"), (70000, "64-bit length")]:
        body = b"x" * size
        opcode, out, consumed = ws.decode_frame(ws.encode_frame(body))
        check("frame round trip " + label,
              out == body and opcode == ws.OP_TEXT and consumed == len(ws.encode_frame(body)))

    masked = ws.encode_frame(payload, mask=True)
    check("masked client frame decodes", ws.decode_frame(masked)[1] == payload)
    check("encode_event produces a decodable text frame",
          ws.decode_message(ws.encode_event({"kind": "ping"}))["kind"] == "ping")

    try:
        ws.decode_frame(ws.encode_frame(b"hello")[:3])
        check("partial frame raises instead of mis-parsing", False, "accepted")
    except ws.WebSocketError:
        check("partial frame raises instead of mis-parsing", True)

    try:
        ws.decode_message(ws.encode_frame(b"{not json"))
        check("invalid JSON message rejected", False, "accepted")
    except ws.WebSocketError:
        check("invalid JSON message rejected", True)

    check("close frame decodes to None", ws.decode_message(ws.encode_frame(b"", ws.OP_CLOSE)) is None)


# --------------------------------------------------------------------------
# 10. HTTP transport (real socket round trip)
# --------------------------------------------------------------------------

def _http(url, payload=None, token=None, method="POST"):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data if method == "POST" else None, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode()), dict(exc.headers)


def test_http_transport():
    svc, _, admin, user, _ = make(command=lambda t: "done: " + t)
    server = ApiServer(svc, port=0).start()
    base = "http://127.0.0.1:" + str(server.port) + "/v1/"
    try:
        code, body, headers = _http(base + "health", method="GET")
        check("HTTP health endpoint works", code == 200 and body["ok"], (code, body))
        check("HTTP responses carry the trace id header", bool(headers.get("X-Trace-Id")), headers)

        code, body, _ = _http(base + "command/execute", {"text": "open notes"}, token=user)
        check("HTTP path maps to a route", code == 200 and "done" in str(body["data"]), (code, body))

        code, body, _ = _http(base + "command/execute", {"text": "x"})
        check("HTTP without a token is 401", code == 401, (code, body))

        code, body, _ = _http(base + "admin/tokens", {}, token=user)
        check("HTTP authorization enforced", code == 403, (code, body))

        req = urllib.request.Request(base + "command/execute", data=b"{bad json", method="POST")
        req.add_header("Authorization", "Bearer " + user)
        try:
            urllib.request.urlopen(req, timeout=5)
            check("malformed JSON body is 400", False, "accepted")
        except urllib.error.HTTPError as exc:
            check("malformed JSON body is 400", exc.code == 400, exc.code)

        code, body, _ = _http("http://127.0.0.1:" + str(server.port) + "/nope", {})
        check("unknown HTTP path is 404", code == 404, (code, body))
    finally:
        server.stop()
        svc.close()
    check("server stops cleanly", server._thread is None)


# --------------------------------------------------------------------------
# 11. observability + audit
# --------------------------------------------------------------------------

def test_observability():
    svc, kernel, _, user, _ = make(command=lambda t: "ok")
    r1 = svc.handle("command.execute", {"text": "a"}, user)
    r2 = svc.handle("task.list", {}, None)

    check("each request gets a distinct trace id", r1["trace_id"] != r2["trace_id"])
    check("envelope reports duration", isinstance(r1["duration_ms"], float))

    log = svc.audit_log()
    check("successes and failures are both audited",
          len(log) >= 2 and any(e["status"] != "ok" for e in log), log[:2])
    check("audit rows carry principal and trace id",
          all(e["trace_id"] for e in log) and any(e["principal"] == "desktop" for e in log), log[:2])
    check("analytics receives api metrics",
          any(row[1].startswith("api.") for row in kernel.analytics.rows), kernel.analytics.rows[:2])

    status = svc.status()
    check("status reports counters", status["requests"] >= 2 and status["active_tokens"] >= 3, status)
    check("health reports available", svc.health()["available"] is True)
    svc.close()


# --------------------------------------------------------------------------
# 12. concurrency
# --------------------------------------------------------------------------

def test_concurrency():
    svc, _, _, user, _ = make()
    results = []
    errors = []

    def worker(i):
        try:
            r = svc.handle("task.create", {"title": "task-" + str(i)}, user)
            results.append(r["ok"])
        except Exception as exc:  # must never escape
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    check("16 concurrent requests all succeed",
          len(results) == 16 and all(results) and not errors, (len(results), errors[:1]))
    ids = {row["trace_id"] for row in svc.audit_log(100)}
    check("concurrent trace ids are unique", len(ids) >= 16, len(ids))
    svc.close()


# --------------------------------------------------------------------------
# 13. persistence across restart
# --------------------------------------------------------------------------

def test_persistence():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_b3g_api.db")
    if os.path.exists(path):
        os.remove(path)
    svc = ApiService(path, kernel=FakeKernel())
    token = svc.issue_token("phone", "device")["token"]
    svc.handle("task.list", {}, token)
    svc.close()

    svc2 = ApiService(path, kernel=FakeKernel())
    ident = svc2.verify_token(token)
    check("tokens survive a restart", ident["principal"] == "phone", ident)
    check("audit log survives a restart", len(svc2.audit_log()) >= 1)
    svc2.revoke_token(ident["token_id"])
    svc2.close()

    svc3 = ApiService(path, kernel=FakeKernel())
    try:
        svc3.verify_token(token)
        check("revocation survives a restart", False, "accepted")
    except ApiError:
        check("revocation survives a restart", True)
    svc3.close()
    os.remove(path)


# --------------------------------------------------------------------------
# 14. task consolidation
# --------------------------------------------------------------------------

def test_task_consolidation():
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import task as legacy

    check("legacy task package still imports", hasattr(legacy, "TaskManager"))
    check("legacy task package re-exports the real implementation",
          legacy.TaskManager is TaskManager and legacy.TaskStore is TaskStore)

    import jarvis_core.tasks as real
    src_dir = os.path.join(ROOT, "task")
    leftovers = [f for f in os.listdir(src_dir) if f.endswith(".py") and f != "__init__.py"]
    check("duplicate task modules removed", leftovers == [], leftovers)
    check("one authoritative task implementation",
          real.TaskManager.__module__ == "jarvis_core.tasks")


def main():
    for fn in [test_validation, test_authentication, test_authorization, test_routing,
               test_policy, test_unavailable, test_error_handling, test_rate_limit,
               test_events, test_websocket_framing, test_http_transport,
               test_observability, test_concurrency, test_persistence,
               test_task_consolidation]:
        try:
            fn()
        except Exception as exc:
            FAILED.append(fn.__name__)
            print("FAIL " + fn.__name__ + " -- crashed: " + type(exc).__name__ + ": " + str(exc))
    print("")
    print(str(len(PASSED)) + " passed, " + str(len(FAILED)) + " failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
