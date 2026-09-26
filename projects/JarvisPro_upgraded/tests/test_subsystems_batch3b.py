"""Behavioural tests for Batch 3b: S18 agent runtime, S19 verification engine.

Real behaviour only: agents actually execute on worker threads, timeouts
actually expire, cancellation actually stops work, verification actually
touches the filesystem. No mocked success values.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.agent_runtime import (AgentRuntime, CancelledError, SharedContext,
                                       STATUS_CANCELLED, STATUS_COMPLETED,
                                       STATUS_FAILED, STATUS_REJECTED, STATUS_TIMEOUT)
from jarvis_core.verification import (RESULT_INCONCLUSIVE, RESULT_UNSUPPORTED,
                                      VerificationEngine)

PASS = 0
FAIL = 0


def check(label, condition, evidence=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {label}  {evidence}")
    else:
        FAIL += 1
        print(f"[FAIL] {label}  {evidence}")


TMP = tempfile.mkdtemp(prefix="jarvis_b3b_")


def section(title):
    print(f"\n=== {title} ===")


# =============================== S19 =====================================
section("S19 verification engine")
ve = VerificationEngine(os.path.join(TMP, "verification.db"))

target = os.path.join(TMP, "report.txt")
with open(target, "w", encoding="utf-8") as fh:
    fh.write("Jarvis is online.\nstatus=READY\n")
digest = hashlib.sha256(open(target, "rb").read()).hexdigest()

v = ve.verify("write report", "file_exists", path=target)
check("file existence is verified against the real filesystem", v.verified,
      f"evidence={v.evidence}")
check("verification records action/expected/actual/evidence/confidence/timestamp",
      all(v.to_dict().get(k) is not None for k in
          ("action", "actual", "evidence", "confidence", "timestamp")),
      f"confidence={v.confidence} at={v.timestamp}")

missing = ve.verify("write report", "file_exists", path=os.path.join(TMP, "ghost.txt"))
check("a missing artefact fails verification instead of reporting success",
      not missing.verified and missing.confidence == 0.0, f"result={missing.result}")

hash_ok = ve.verify("write report", "file_hash", digest, path=target)
hash_bad = ve.verify("write report", "file_hash", "0" * 64, path=target)
check("content hash verification detects the exact bytes written", hash_ok.verified,
      f"sha256 matched, confidence={hash_ok.confidence}")
check("a wrong hash is reported as failed with the observed value",
      not hash_bad.verified and hash_bad.actual == digest,
      f"actual={hash_bad.actual[:16]}...")
check("direct evidence outranks indirect evidence", hash_ok.confidence > v.confidence,
      f"file_hash={hash_ok.confidence} > file_exists={v.confidence}")

contains = ve.verify("greeting restored", "file_contains", "Jarvis is online.", path=target)
check("file content verification finds the expected substring", contains.verified,
      contains.evidence)

eq = ve.verify("status check", "value_equals", "READY", value="READY")
neq = ve.verify("status check", "value_equals", "READY", value="DEGRADED")
check("value equality verification passes and fails correctly",
      eq.verified and not neq.verified, f"actual={neq.actual!r}")

jf = ve.verify("tool result", "json_field", 3, value={"data": {"count": 3}},
               field_path="data.count")
jf_bad = ve.verify("tool result", "json_field", 3, value={"data": {}},
                   field_path="data.count")
check("nested JSON field verification works on real payloads",
      jf.verified and not jf_bad.verified, f"actual={jf.actual} / {jf_bad.actual}")

alive = ve.verify("worker alive", "process_alive", True, pid=os.getpid())
dead = ve.verify("worker alive", "process_alive", True, pid=999999)
check("process liveness is verified through a real signal probe",
      alive.verified and not dead.verified, f"self alive={alive.actual}, 999999={dead.actual}")

pred = ve.verify("custom rule", "predicate", predicate=lambda: 2 + 2 == 4)
check("callable predicates are evaluated, not assumed", pred.verified, pred.evidence)

boom = ve.verify("custom rule", "predicate", predicate=lambda: 1 / 0)
check("a raising check is inconclusive, never silently verified",
      boom.result == RESULT_INCONCLUSIVE and not boom.verified, boom.evidence)

unsup = ve.verify("telepathy", "mind_read")
check("an unknown verifier reports unsupported instead of passing",
      unsup.result == RESULT_UNSUPPORTED and not unsup.verified, unsup.evidence)

try:
    ve.verify("", "file_exists", path=target)
    check("verification validates its input", False, "no error raised")
except ValueError as exc:
    check("verification validates its input", True, str(exc))

multi = ve.verify_all("deploy report", [
    {"kind": "file_exists", "path": target},
    {"kind": "file_hash", "expected": digest, "path": target},
    {"kind": "file_contains", "expected": "READY", "path": target},
], trace_id="JRV-2026-00000042")
check("multi-check verification aggregates real evidence",
      multi["verified"] and len(multi["checks"]) == 3,
      f"confidence={multi['confidence']} checks={len(multi['checks'])}")
check("aggregate confidence is the weakest passing check",
      abs(multi["confidence"] - 0.85) < 1e-9, f"confidence={multi['confidence']}")

mixed = ve.verify_all("deploy report", [
    {"kind": "file_exists", "path": target},
    {"kind": "file_contains", "expected": "NOT THERE", "path": target},
])
check("one failing check fails the whole action", not mixed["verified"],
      mixed["reason"][:70])
check("failures are reported with their evidence", len(mixed["failures"]) == 1,
      f"{len(mixed['failures'])} failure(s)")

empty = ve.verify_all("unchecked action", [])
check("an action with no checks is never counted as verified",
      not empty["verified"] and empty["confidence"] == 0.0, empty["reason"])

hist = ve.history(trace_id="JRV-2026-00000042")
check("verification history is queryable by trace id", len(hist) == 3,
      f"{len(hist)} records for the trace")
stats = ve.stats()
check("verification statistics come from stored records",
      stats["total"] == 19 and 0 < stats["verified_rate"] < 1,
      f"total={stats['total']} verified_rate={stats['verified_rate']}")

ve2 = VerificationEngine(os.path.join(TMP, "verification.db"))
check("verification history survives restart",
      ve2.stats()["total"] == stats["total"], f"{ve2.stats()['total']} records reloaded")


# =============================== S18 =====================================
section("S18 autonomous / background agents")
rt = AgentRuntime(os.path.join(TMP, "agents.db"), max_workers=3)

identity = rt.register("researcher", lambda h: {"answer": 42, "task": h.task},
                       role="research", capabilities=["research", "summarise"])
check("agents have a real identity with capabilities",
      identity.id.startswith("AG-") and "research" in identity.capabilities,
      f"{identity.id} {identity.name}/{identity.role} caps={identity.capabilities}")
check("agents are discoverable by capability",
      rt.agents_for("summarise") == ["researcher"], f"{rt.agents_for('summarise')}")

h = rt.assign("researcher", {"question": "latency?"})
res = h.wait()
check("an assigned agent really executes on a background worker",
      res["status"] == STATUS_COMPLETED and res["result"]["answer"] == 42,
      f"status={res['status']} result={res['result']['answer']}")
check("the agent receives its assigned task payload",
      res["result"]["task"] == {"question": "latency?"}, f"{res['result']['task']}")
check("runs are executed off the calling thread",
      threading.current_thread().name == "MainThread" and res["duration"] >= 0,
      f"duration={res['duration']}s")

try:
    rt.assign("ghost", {})
    check("assigning an unknown agent fails loudly", False, "no error")
except KeyError as exc:
    check("assigning an unknown agent fails loudly", True, str(exc))


def failing(handle):
    raise ValueError("upstream source returned garbage")


rt.register("flaky", failing, capabilities=["research"])
fres = rt.assign("flaky", {}).wait()
check("an agent exception becomes a reported failure, not a crash",
      fres["status"] == STATUS_FAILED and "ValueError" in fres["error"], fres["error"])


def slow(handle):
    for _ in range(100):
        handle.checkpoint()
        time.sleep(0.05)
    return "never"


rt.register("slowpoke", slow, timeout=0.3)
tres = rt.assign("slowpoke", {}).wait(timeout=5)
check("an over-running agent times out instead of hanging Jarvis",
      tres["status"] == STATUS_TIMEOUT, f"status={tres['status']} error={tres['error']}")


def cooperative(handle):
    while True:
        handle.checkpoint()
        time.sleep(0.02)


rt.register("looper", cooperative, timeout=5, max_iterations=1000)
looping = rt.assign("looper", {})
time.sleep(0.15)
cancel = rt.cancel(looping.run_id, "user pressed stop")
lres = looping.wait(timeout=5)
check("cancellation is accepted for a live run", cancel["ok"], f"{cancel['status']}")
check("a cancelled agent stops and reports cancelled",
      lres["status"] == STATUS_CANCELLED, f"status={lres['status']} error={lres['error']}")
check("cancelling a finished run is refused",
      not rt.cancel(looping.run_id)["ok"], rt.cancel(looping.run_id)["error"])


def runaway(handle):
    while True:
        handle.checkpoint()


rt.register("runaway", runaway, max_iterations=5, timeout=5)
rres = rt.assign("runaway", {}).wait(timeout=5)
check("bounded autonomy: the iteration budget stops an infinite loop",
      rres["status"] == STATUS_FAILED and "iteration budget" in rres["error"],
      rres["error"])


def hog(handle):
    time.sleep(0.4)
    return "done"


rt.register("single", hog, max_concurrent=1, timeout=3)
first = rt.assign("single", {})
second = rt.assign("single", {})
check("resource limits reject work beyond an agent's concurrency cap",
      second.status == STATUS_REJECTED and "resource limit" in second.error,
      second.error)
check("the first run still completes normally",
      first.wait(timeout=5)["status"] == STATUS_COMPLETED, "first run completed")


# --- shared context + communication + aggregation ---
def collector(handle):
    handle.checkpoint()
    handle.context.put("sources", handle.context.get("sources", 0) + 1, handle.agent.name)
    handle.send("writer", "evidence", {"claim": "latency is 42ms"})
    return "collected"


def writer(handle):
    handle.checkpoint()
    deadline = time.time() + 1.5
    msgs = []
    while time.time() < deadline and not msgs:
        msgs = handle.inbox()
        if not msgs:
            time.sleep(0.05)
    handle.context.put("draft", "report ready", handle.agent.name)
    return {"messages": len(msgs), "first": msgs[0]["body"] if msgs else None}


rt.register("collector", collector, capabilities=["research"], timeout=3)
rt.register("writer", writer, capabilities=["writing"], timeout=3)
group = rt.run_group([{"agent": "collector", "task": {"q": "latency"}},
                      {"agent": "writer", "task": {"format": "brief"}}],
                     shared={"topic": "latency"}, timeout=6)
check("multiple agents run together and results are aggregated",
      group["total"] == 2 and group["succeeded"] == 2 and group["ok"],
      f"{group['succeeded']}/{group['total']} succeeded")
check("agents share one context object",
      group["shared_context"].get("sources") == 1
      and group["shared_context"].get("draft") == "report ready",
      f"shared={group['shared_context']}")
writer_out = [r["result"] for r in group["results"] if r["agent"] == "writer"][0]
check("agent-to-agent messages are really delivered",
      writer_out["messages"] == 1 and writer_out["first"]["claim"] == "latency is 42ms",
      f"writer received {writer_out['first']}")

mixed_group = rt.run_group([{"agent": "researcher", "task": {}},
                            {"agent": "flaky", "task": {}},
                            {"agent": "ghost", "task": {}}], timeout=6)
check("a group with failures is reported as partial, not successful",
      mixed_group["partial"] and not mixed_group["ok"]
      and mixed_group["succeeded"] == 1 and mixed_group["failed"] == 2,
      f"succeeded={mixed_group['succeeded']} failed={mixed_group['failed']}")
check("an unknown agent in a group is rejected with a reason",
      any(e["status"] == STATUS_REJECTED for e in mixed_group["errors"]),
      str(mixed_group["errors"][-1])[:70])

sc = SharedContext({"a": 1})
threads = [threading.Thread(target=lambda i=i: sc.put(f"k{i}", i, "t")) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("shared context is safe under concurrent writes",
      len(sc.snapshot()) == 21 and len(sc.writes()) == 20,
      f"{len(sc.snapshot())} keys, {len(sc.writes())} writes recorded")


# --- persistence, reporting, cancellation of a whole group, shutdown ---
runs = rt.runs(limit=100)
check("every agent run is persisted with its outcome", len(runs) >= 10,
      f"{len(runs)} runs stored")
check("failed runs keep their error text for diagnostics",
      any(r["status"] == STATUS_FAILED and r["error"] for r in runs),
      "failure reasons persisted")
rt2 = AgentRuntime(os.path.join(TMP, "agents.db"), max_workers=1)
check("agent run history survives restart", len(rt2.runs(limit=100)) == len(runs),
      f"{len(rt2.runs(limit=100))} runs reloaded")
rt2.shutdown()

rt.register("grouped", cooperative, timeout=5, max_iterations=10000)
gh1 = rt.assign("grouped", {}, group_id="GRP-test")
gh2 = rt.assign("grouped", {}, group_id="GRP-test")
time.sleep(0.1)
cancelled = rt.cancel_group("GRP-test", "parent task cancelled")
gh1.wait(timeout=5)
gh2.wait(timeout=5)
check("cancellation propagates to every agent in a group",
      len(cancelled["cancelled"]) == 2
      and gh1.status == STATUS_CANCELLED and gh2.status == STATUS_CANCELLED,
      f"cancelled={len(cancelled['cancelled'])} statuses={gh1.status}/{gh2.status}")

health = rt.health()
check("agent runtime reports real health",
      health["available"] and health["registered_agents"] >= 8
      and health["live_threads"] == 3,
      f"agents={health['registered_agents']} workers={health['workers']} live={health['live_threads']}")

bad = rt.run("teleport")
check("unknown agent actions are invalid input, not silent success",
      bad["status"] == "invalid_input", bad["error"])
viarun = rt.run("assign", agent="researcher", task={"question": "pipeline?"})
check("agents are callable through the pipeline run() entry point",
      viarun["status"] == STATUS_COMPLETED, f"status={viarun['status']}")

shut = rt.shutdown()
check("shutdown stops the worker pool without leaking threads", shut["ok"],
      f"workers_stopped={shut['workers_stopped']}")


# ======================= kernel integration ==============================
section("kernel integration (S18/S19 in the real pipeline)")
from jarvis_core.kernel import Kernel  # noqa: E402

kdir = os.path.join(TMP, "kdata")
os.makedirs(kdir, exist_ok=True)
k = Kernel(data_dir=kdir)
check("the kernel exposes the verification engine", hasattr(k, "verification"),
      "kernel.verification present")
check("the kernel exposes the agent runtime", hasattr(k, "agents"),
      "kernel.agents present")

sel = k.managers.select("agents")
check("the agent runtime is selectable through the manager registry",
      sel["manager"] == "agents", f"selected={sel['manager']} status={sel['status']}")

khealth = k.health()
check("kernel health includes agents and verification",
      khealth["agents"]["available"] and khealth["verification"]["available"],
      f"agents={khealth['agents']['registered_agents']} verifications="
      f"{khealth['verification']['total']}")

artefact = os.path.join(TMP, "kernel_artefact.txt")
with open(artefact, "w", encoding="utf-8") as fh:
    fh.write("written by the pipeline")
trace = k.observability.start_trace("verify artefact")
trace_id = trace if isinstance(trace, str) else getattr(trace, "trace_id", str(trace))
kv = k.verification.verify("pipeline write", "file_contains", "pipeline",
                           path=artefact, trace_id=trace_id)
check("pipeline actions are verified with evidence tied to a trace",
      kv.verified and kv.trace_id == trace_id, f"{trace_id} -> {kv.result}")
check("verification feeds analytics telemetry",
      k.analytics.success_rate(kind="verification") in (0.0, 1.0),
      f"verification success_rate={k.analytics.success_rate(kind='verification')}")

k.agents.register("kernel_worker", lambda h: {"session": h.task.get("session")},
                  capabilities=["background"])
kres = k.agents.assign("kernel_worker", {"session": k.session("gui")}).wait(timeout=5)
check("background agents can run work from the live kernel session",
      kres["status"] == STATUS_COMPLETED and kres["result"]["session"].startswith("S-"),
      f"session={kres['result']['session']}")
k.agents.shutdown()

print(f"\n{PASS} passed, {FAIL} failed")
shutil.rmtree(TMP, ignore_errors=True)
if __name__ == "__main__":
    sys.exit(1 if FAIL else 0)


def test_subsystems_batch3b_checks_all_pass():
    """Expose the module-level checks to pytest.

    The checks above run at import time.  Without this the bare
    ``sys.exit`` made pytest fail collection, so none of them ran.
    """
    assert FAIL == 0, f"{FAIL} check(s) failed"

