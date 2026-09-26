"""Behavioural verification for the S1/S2/S9/S10/S11/S16/S17/S24/S32/S39 kernel.

Run: python3 tests/test_kernel_batch1.py   (no pytest needed in this sandbox)
Every check asserts real behaviour, not the existence of a symbol.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.analytics import Analytics, ResourceMonitor  # noqa: E402
from jarvis_core.decisions import ContextEngine, DecisionEngine, ManagerRegistry  # noqa: E402
from jarvis_core.graph import CycleError, DependencyGraph  # noqa: E402
from jarvis_core.kernel import Kernel  # noqa: E402
from jarvis_core.observability import Observability  # noqa: E402
from jarvis_core.policy import PolicyEngine, redact  # noqa: E402
from jarvis_core.tasks import COMPLETED, FAILED, RUNNING, TaskManager, TaskStore, StateError  # noqa: E402

PASS: list = []
FAIL: list = []


def check(name, cond, evidence=""):
    (PASS if cond else FAIL).append((name, evidence))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {evidence}")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="jarvis_kernel_")
    try:
        # ---------------- S39 observability ----------------
        obs = Observability(os.path.join(tmp, "obs.db"))
        tid = obs.start_trace("open calculator")
        check("S39 trace id format", tid.startswith("JRV-") and tid.split("-")[2].isdigit()
              and len(tid.split("-")[2]) == 8, tid)
        with obs.span("input", "stt"):
            with obs.span("router", "route", intent="app.open"):
                with obs.span("manager", "automation"):
                    with obs.span("tool", "launch_app"):
                        pass
        try:
            with obs.span("database", "write_memory"):
                raise IOError("disk full")
        except IOError:
            pass
        obs.record_event("output", "tts")
        obs.end_trace(tid, "error")
        chain = obs.chain(tid)
        check("S39 execution trace chain", chain[:3] == ["input", "router", "manager"] and "output" in chain,
              " -> ".join(chain))
        rep = obs.failure_report(tid)
        check("S39 failure report captures real error", rep["count"] == 1 and "disk full" in rep["failures"][0]["error"],
              rep["failures"][0]["error"])
        tid2 = obs.start_trace("second")
        check("S39 monotonic trace ids", int(tid2.split("-")[2]) == int(tid.split("-")[2]) + 1, f"{tid} -> {tid2}")
        obs.end_trace(tid2)
        check("S39 nested spans are parented", any(s["parent_id"] for s in obs.get_trace(tid)["spans"]),
              f"{len(obs.get_trace(tid)['spans'])} spans")
        check("S39 health reports error rate", obs.health()["error_rate"] > 0, str(obs.health()["error_rate"]))

        # ---------------- S1 dependency graph ----------------
        g = DependencyGraph()
        for n in "abcd":
            g.add_node(n, "task", f"task {n}", cost=1.0)
        g.add_dependency("a", "b")
        g.add_dependency("b", "c")
        g.add_dependency("a", "d")
        waves = g.execution_waves()
        check("S1 execution waves respect dependencies", waves == [["a"], ["b", "d"], ["c"]], str(waves))
        cycle_rejected = False
        try:
            g.add_dependency("c", "a")
        except CycleError as exc:
            cycle_rejected = "cycle" in str(exc)
        check("S1 cycle rejected", cycle_rejected, "c -> a refused")
        check("S1 graph unchanged after rejection", g.execution_waves() == waves, str(g.execution_waves()))
        imp = g.impact_of("a")
        check("S1 change impact analysis", imp["blast_radius"] == 3 and set(imp["transitive"]) == {"b", "c", "d"},
              str(imp["transitive"]))
        cp = g.critical_path()
        check("S1 critical path", cp["path"] == ["a", "b", "c"], str(cp))
        viz = g.render_ascii()
        check("S1 plan visualization inspectable", "wave 1" in viz and "critical path" in viz,
              viz.splitlines()[0])
        check("S1 dot export", g.to_dot().startswith("digraph plan"), "dot ok")

        # ---------------- S11 permissions ----------------
        pol = PolicyEngine(os.path.join(tmp, "pol.db"))
        perm = pol.grant_temporary("owner", "files.*", ttl_seconds=0.6, reason="cleanup")
        d1 = pol.check("owner", "files.write", "write notes.txt")
        check("S11 wildcard temp permission allows", d1.allowed, d1.effect)
        time.sleep(0.8)
        d2 = pol.check("owner", "files.write", "write notes.txt")
        check("S11 permission expiry actually denies", not d2.allowed,
              f"{d2.effect}: {d2.reasons[-1]}")
        check("S11 purge marks expired revoked", pol.purge_expired() >= 1, "purged")
        pol.grant("owner", "memory.read", reason="gui")
        check("S11 non-expiring permission still valid", pol.check("owner", "memory.read").allowed, "allow")
        cls = pol.classify("please rm -rf / now", "files.delete")
        check("S11 risk classification of destructive command",
              cls["risk"] == "critical" and cls["protected"], cls["risk"])
        d3 = pol.check("owner", "files.delete", "rm -rf /")
        check("S11 protected op needs approval even with permission", d3.effect == "ask", d3.effect)

        # ---------------- S1 approval checkpoints ----------------
        seen = {}
        pol.set_approval_hook(lambda r: seen.update({"id": r.request_id, "summary": r.summary}))
        req = pol.request_approval("system.shutdown", "shutdown the PC", "high", timeout=5.0)
        check("S1 approval hook fired for GUI", seen.get("id") == req.request_id, seen.get("summary", ""))
        threading.Timer(0.2, lambda: pol.resolve_approval(req.request_id, True, "krishna")).start()
        res = pol.wait_for_approval(req)
        check("S1 approval unblocks action", res["approved"] and res["approved_by"] == "krishna", res["state"])
        req2 = pol.request_approval("system.format", "format C:", "critical", timeout=0.4)
        res2 = pol.wait_for_approval(req2)
        check("S1 approval timeout blocks action", not res2["approved"] and res2["state"] == "timeout",
              res2["state"])
        g1 = pol.guard("owner", "network.read", "fetch weather")
        check("S11 guard allows low risk", g1["allowed"], g1["decision"]["risk"])

        # ---------------- S24 audit ----------------
        pol.audit("owner", command="login token=abc123 password=hunter2", tool="browser",
                  scope="browser.form", decision="allow", risk="medium", result="ok",
                  trace_id=tid, api_key="sk-live-999")
        log = pol.audit_log(limit=5)
        entry = log[0]
        check("S24 audit log records trace/user/command/decision",
              entry["trace_id"] == tid and entry["decision"] == "allow" and entry["tool"] == "browser",
              entry["scope"])
        check("S24 secrets redacted in audit",
              "hunter2" not in entry["command"] and "abc123" not in entry["command"]
              and "sk-live-999" not in entry["extra"], entry["command"])
        check("S24 redact helper on dicts", redact({"password": "x", "note": "ok"})["password"] == "***REDACTED***",
              "dict redaction")

        # ---------------- S9/S10 tasks ----------------
        store = TaskStore(os.path.join(tmp, "tasks.db"))
        tm = TaskManager(store)
        root = tm.create("deploy site", kind="generic", manager="coding")
        build = tm.subtask(root.task_id, "build", kind="generic")
        test = tm.create("test", depends_on=[build.task_id])
        check("S9 dependency registered", tm.graph.dependencies_of(test.task_id) == [build.task_id],
              build.task_id)
        cyc = False
        try:
            tm.graph.add_dependency(test.task_id, build.task_id)
        except CycleError:
            cyc = True
        check("S9 task cycle rejected", cyc, "refused")
        r = tm.run(test.task_id, lambda: "never")
        check("S9 unmet dependency blocks execution", not r["ok"] and "unmet" in r["error"], r["error"])
        r2 = tm.run(build.task_id, lambda: "artifact.zip")
        check("S9 successful run records result", r2["ok"] and tm.get(build.task_id).state == COMPLETED,
              str(r2["result"]))
        tm.transition(test.task_id, "queued", "reset")
        r3 = tm.run(test.task_id, lambda: "tests green")
        check("S9 runs once dependency completed", r3["ok"], str(r3["result"]))

        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("network blip")
            return "ok after retry"

        flake = tm.create("flaky fetch", max_retries=3)
        rf = tm.run(flake.task_id, flaky)
        check("S9 retry with failure reason", rf["ok"] and attempts["n"] == 3, f"attempts={attempts['n']}")

        boom = tm.create("bad task", max_retries=0)
        rb = tm.run(boom.task_id, lambda: (_ for _ in ()).throw(ValueError("bad input")))
        check("S9 failure reason stored", tm.get(boom.task_id).failure_reason.startswith("ValueError"),
              tm.get(boom.task_id).failure_reason)
        hist = tm.history(boom.task_id)
        check("S9 execution history recorded", len(hist) >= 3 and hist[0]["to_state"] == "created",
              f"{len(hist)} transitions")
        bad_transition = False
        try:
            tm.transition(boom.task_id, COMPLETED)
        except StateError:
            bad_transition = True
        check("S9 state machine rejects illegal transition", bad_transition, "failed -> completed refused")

        rolled = {"done": []}
        tm.register_rollback(build.task_id, lambda t: rolled["done"].append(t.task_id))
        rr = tm.rollback(build.task_id, "deploy aborted")
        check("S9 rollback runs handler and sets state",
              rolled["done"] == [build.task_id] and tm.get(build.task_id).state == "rolled_back", str(rr))

        # cancellation propagation
        p = tm.create("long job")
        c1 = tm.subtask(p.task_id, "child 1")
        c2 = tm.subtask(c1.task_id, "grandchild")
        dep = tm.create("dependent", depends_on=[p.task_id])
        canc = tm.cancel(p.task_id, "user pressed stop")
        check("S1 cancellation propagates to children and dependents",
              set(canc["cancelled"]) == {p.task_id, c1.task_id, c2.task_id, dep.task_id},
              f"{canc['count']} tasks")
        check("S1 cancel token visible to workers", tm.is_cancelled(c2.task_id), "token set")

        # crash recovery
        safe = tm.create("index files", kind="generic")
        danger = tm.create("delete old backups", kind="delete")
        for t in (safe, danger):
            tm.transition(t.task_id, "queued")
            tm.transition(t.task_id, RUNNING)
        tm2 = TaskManager(TaskStore(os.path.join(tmp, "tasks.db")))
        rec = tm2.recover()
        check("S10 crash recovery resumes safe task", safe.task_id in rec["resumed"], str(rec["resumed"]))
        check("S10 crash recovery quarantines destructive task",
              danger.task_id in rec["quarantined"], str(rec["quarantined"]))
        check("S10 persistent execution survives restart",
              tm2.get(build.task_id).state == "rolled_back", "state reloaded from disk")

        # ---------------- S16 managers + fallback ----------------
        reg = ManagerRegistry()

        class Primary:
            def search(self, q):
                raise RuntimeError("primary offline")

        class Backup:
            def search(self, q):
                return f"results for {q}"

        reg.register("primary_research", Primary(), ["research"], probe=lambda: True)
        reg.register("backup_research", Backup(), ["research"], dependencies=["network"])
        out = reg.execute_with_fallback("research", "search", "jarvis")
        check("S1 fallback manager selection works",
              out["ok"] and out["manager"] == "backup_research" and out["fallbacks_used"] == 1,
              f"{out['attempts']}")
        hc = reg.health_check()
        check("S16 manager health check reports degraded/failed + missing deps",
              hc["primary_research"]["status"] in ("degraded", "failed")
              and hc["backup_research"]["missing_dependencies"] == ["network"]
              and hc["backup_research"]["success_rate"] == 1.0,
              f"primary={hc['primary_research']['status']} backup={hc['backup_research']['status']}"
              f" missing={hc['backup_research']['missing_dependencies']}")
        check("S16 health exposes last success/failure",
              hc["primary_research"]["last_failure"] and hc["backup_research"]["last_success"],
              "timestamps present")
        sel = reg.select("research")
        check("S16 selection prefers healthy manager", sel["manager"] == "backup_research", sel["reason"])

        # ---------------- S1 decision explanation ----------------
        de = DecisionEngine()
        exp = de.decide(
            {"research": {"capability": 0.9, "health": 1.0, "cost": 0.3},
             "browser": {"capability": 0.5, "health": 0.6, "cost": 0.8}},
            weights={"capability": 2.0, "health": 1.5, "cost": -1.0},
            context_used=["user asked a factual question"],
        )
        check("S1 decision explanation picks and justifies",
              exp.choice == "research" and 0.5 < exp.confidence <= 1.0
              and "Because:" in exp.to_text(), f"conf {exp.confidence}")
        check("S1 explanation lists alternatives", exp.alternatives[0]["option"] == "browser",
              str(exp.alternatives))
        check("S1 decision history queryable", de.explain_last().startswith("Chose 'research'"), "history ok")

        # ---------------- S2 context conflicts ----------------
        ctx = ContextEngine()
        ctx.add("editor", "vscode", "memory", 0.8)
        ctx.add("editor", "notepad", "inference", 0.9)
        res = ctx.resolve("editor")
        check("S2 conflict resolved by source priority",
              res["value"] == "vscode" and res["conflict"] and res["overridden"], res["reason"])
        ctx.add("editor", "pycharm", "user_correction", 1.0)
        res2 = ctx.resolve("editor")
        check("S2 explicit user correction wins", res2["value"] == "pycharm", res2["reason"])
        ctx.add("foreground_app", "chrome", "environment", 0.9, ttl=0.3)
        time.sleep(0.4)
        check("S2 context expiration", ctx.resolve("foreground_app")["value"] is None, "expired")
        asm = ctx.assemble(budget=2)
        check("S2 context assembly ranks and compresses",
              "editor" in asm["context"] and "editor" in asm["conflicts"], asm["compressed"])
        exp2 = ctx.decide_with_context(de, {"open_vscode": {"fit": 0.9}, "open_notepad": {"fit": 0.2}})
        check("S2 context-aware decision records context used",
              exp2.choice == "open_vscode" and exp2.context_used, str(exp2.context_used))

        # ---------------- S32 analytics ----------------
        an = Analytics(os.path.join(tmp, "an.db"))
        for i in range(8):
            an.record("command", "open calculator", success=i % 4 != 0, duration_ms=10 + i,
                      corrected=(i == 0))
        an.record("manager", "automation", True, 12.0)
        an.record("manager", "automation", False, 30.0)
        an.record("manager", "research", True, 90.0)
        an.record("tool", "launch_app", True, 5.0)
        an.record("model", "llama3-local", True, 800.0, cost=0.0)
        an.record("model", "llama3-local", False, 900.0, cost=0.0)
        an.record("learning", "experience_saved", True)
        an.record("prediction", "next_action", True)
        an.record("prediction", "next_action", False)
        check("S32 success rate from real events", an.success_rate("command") == 0.75,
              str(an.success_rate("command")))
        check("S32 failure rate", an.failure_rate("command") == 0.25, str(an.failure_rate("command")))
        ms = {m["name"]: m["success_score"] for m in an.manager_scores()}
        check("S32 manager success score", ms["automation"] == 0.5 and ms["research"] == 1.0, str(ms))
        check("S32 model success + usage stats",
              an.model_scores()[0]["success_score"] == 0.5 and an.ai_usage()["llama3-local"]["calls"] == 2,
              str(an.ai_usage()))
        check("S32 prediction accuracy", an.learning_stats()["prediction_accuracy"] == 0.5,
              str(an.learning_stats()["prediction_accuracy"]))
        check("S32 user correction rate", an.user_correction_rate() == 0.125, str(an.user_correction_rate()))
        with an.timer("tool", "screenshot"):
            time.sleep(0.01)
        check("S32 timer records duration", an.scores("tool")[0]["avg_ms"] > 0, "timed")
        dash = an.dashboard()
        check("S32 dashboard aggregates everything",
              dash["overall"]["total"] >= 15 and dash["most_used_commands"], str(dash["overall"]["total"]))

        # ---------------- S17 resources ----------------
        rm = ResourceMonitor(cpu_limit=100.0, ram_limit=100.0)
        snap = rm.health()
        check("S17 live system stats (not hardcoded)",
              snap["cores"] and snap["memory"]["total_mb"] and snap["disk"]["total_gb"]
              and snap["system_health"] in ("Excellent", "Good", "Degraded", "Critical"),
              f"cpu={snap['cpu_percent']} mem={snap['memory']['percent']}% health={snap['system_health']}")
        strict = ResourceMonitor(cpu_limit=-1.0)
        check("S17 resource-aware admission refuses under pressure",
              strict.admit({})["admitted"] is False, strict.admit({})["reason"])
        check("S17 admission allows when budget fits", rm.admit({"ram_mb": 1})["admitted"], "admitted")
        huge = rm.admit({"ram_mb": 10 ** 9})
        check("S17 refuses impossible memory request", not huge["admitted"], huge["reason"])
        check("S17 battery absence reported honestly",
              rm.battery()["available"] in (True, False), str(rm.battery()))

        # ---------------- kernel wiring ----------------
        k = Kernel(data_dir=tmp)
        t = k.begin("kernel smoke")
        with k.observability.span("router", "route"):
            pass
        k.observability.end_trace(t)
        k.policy.grant("owner", "memory.read", reason="kernel test")
        gd = k.guard("memory.read", "show memory")
        health = k.health()
        check("kernel single object graph wired",
              gd["allowed"] and "observability" in health and "resources" in health
              and health["tasks"]["total"] >= 0, t)
        rec2 = k.recover()
        check("kernel startup recovery runs", "tasks" in rec2 and "permissions_expired" in rec2, str(rec2))

        print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
        for n, e in FAIL:
            print("  FAILED:", n, e)
        return 0 if not FAIL else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
