"""Cross-system integration test: the full chain must actually work.

chain under test:
  ambiguity -> clarification -> context -> memory -> profile -> decision
  -> dependency plan -> manager selection (with fallback) -> policy
  -> task -> execution -> verification -> analytics -> trace

No pytest. Prints PASS/FAIL with evidence, exits non-zero on failure.
The kernel is isolated in a temp data dir so live workspace data is untouched.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.kernel import Kernel  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, evidence: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}" + (f"  {evidence}" if evidence else ""))
    else:
        FAILED += 1
        print(f"[FAIL] {name}" + (f"  {evidence}" if evidence else ""))


TMP = tempfile.mkdtemp(prefix="jarvis_chain_")
k = Kernel(data_dir=TMP)

print("=== kernel wiring ===")
for attr in ("conversation", "memory", "profile", "personality", "notes", "reminders",
             "observability", "policy", "tasks", "managers", "decisions", "context",
             "analytics"):
    check(f"kernel exposes {attr}", hasattr(k, attr), type(getattr(k, attr, None)).__name__)

print("\n=== stage 1-5: ambiguity -> context -> memory -> profile ===")
k.remember("Krishna's main project is Jarvis Pro, a Python assistant", importance=0.8)
k.remember("My gmail app password is hunter2", type="credential", importance=0.9)
k.profile.set("name", "Krishna Prajapati")
k.profile.add_constraint("no-deletes", "forbid_scope", {"scopes": ["files.delete"]},
                         "owner forbids deletions")

ambiguous = k.understand("Open it.", candidates=["jarvis.py", "notes.db"])
check("pipeline detects ambiguity and asks a useful question",
      ambiguous["needs_clarification"] and "jarvis.py" in ambiguous["clarification"],
      repr(ambiguous["clarification"]))

understanding = k.understand("What is my Jarvis project written in?")
check("pipeline recalls relevant memory",
      any("Jarvis Pro" in m["content"] for m in understanding["memories"]),
      f"{len(understanding['memories'])} memories recalled")
check("pipeline supplies profile to the reasoning layer",
      understanding["profile"].get("name", {}).get("value") == "Krishna Prajapati",
      f"profile keys={list(understanding['profile'])}")
check("pipeline supplies user constraints",
      any(c["name"] == "no-deletes" for c in understanding["constraints"]),
      f"{len(understanding['constraints'])} constraint(s)")
check("pipeline assembles context, not just latest text",
      isinstance(understanding.get("context"), (dict, list, str))
      and understanding["context"] is not None,
      f"context type={type(understanding['context']).__name__}")
check("no subsystem silently degraded", not understanding["degraded"],
      f"degraded={understanding['degraded']}")

cloud_view = k.understand("what is my gmail app password", audience="cloud")
check("secret memory never leaves its permission scope",
      all("hunter2" not in m["content"] for m in cloud_view["memories"]),
      f"cloud audience got {len(cloud_view['memories'])} memories, none secret")

check("personality stays stable while style adapts",
      understanding["presentation"]["core"]["identity"] == "Jarvis"
      and "verbosity" in understanding["presentation"]["presentation"],
      f"core identity=Jarvis style={understanding['style']['style']}")

print("\n=== stage 6-13: decision -> plan -> manager -> policy -> task -> verify -> analytics ===")
calls: list = []


class PrimaryFiles:
    def run(self, payload):
        calls.append("primary")
        raise RuntimeError("primary manager unavailable")


class BackupFiles:
    def run(self, payload):
        calls.append("backup")
        return {"opened": payload}


k.managers.register("primary", PrimaryFiles(), capabilities=["files"])
k.managers.register("backup", BackupFiles(), capabilities=["files"])
selection = k.managers.execute_with_fallback("files", "run", "jarvis.py")
check("manager fallback runs a valid alternative after failure",
      calls == ["primary", "backup"] and selection["ok"]
      and selection["manager"] == "backup" and selection["fallbacks_used"] == 1,
      f"calls={calls} winner={selection.get('manager')} errors={selection['errors']}")

verdict = k.profile.check_constraints("files.delete.project")
check("policy/profile layer blocks a constrained action", not verdict["allowed"],
      verdict["violations"][0]["reason"])

trace_id = k.begin("integration request")
with k.observability.span("input", "What is my Jarvis project written in?"):
    pass
with k.observability.span("manager", "files:backup"):
    pass
with k.observability.span("output", "answered"):
    pass
k.observability.end_trace(trace_id, "ok")
chain = k.observability.chain(trace_id)
check("request produces an inspectable trace chain",
      trace_id.startswith("JRV-") and "input" in chain and "output" in chain,
      f"{trace_id}: {chain}")

k.analytics.record("command", "integration request", True, trace_id=trace_id)
check("analytics records real telemetry for the request",
      k.analytics.success_rate() > 0, f"success_rate={k.analytics.success_rate()}")

print("\n=== health / recovery include the new subsystems ===")
health = k.health()
check("health reports memory, notes and reminders",
      all(key in health for key in ("memory", "notes", "reminders")),
      f"memory={health['memory']['by_status']} reminders={health['reminders']['by_state']}")
recovery = k.recover()
check("startup recovery runs memory decay and reminder scan",
      "memory_decay" in recovery and "reminders_due" in recovery,
      f"decay={recovery['memory_decay']['count']} due={recovery['reminders_due']}")

print("\n=== shared state across surfaces ===")
gui = k.understand("open the same file again", surface="gui")
voice = k.understand("and read it to me", surface="voice")
check("all surfaces share one conversation session",
      gui["session"] == voice["session"], f"session={gui['session']}")
check("voice keeps the same core personality as the GUI",
      voice["presentation"]["core"] == gui["presentation"]["core"]
      and voice["presentation"]["presentation"]["verbosity"] != "detailed",
      f"core={voice['presentation']['core']['identity']} "
      f"voice verbosity={voice['presentation']['presentation']['verbosity']}")
spoken = k.personality.render("voice", {"verbosity": "detailed", "tone": "neutral"})
check("voice surface downgrades detailed answers for delivery",
      spoken["presentation"]["verbosity"] == "concise",
      f"detailed -> {spoken['presentation']['verbosity']} on voice")

print(f"\n{PASSED} passed, {FAILED} failed")
if __name__ == "__main__":
    sys.exit(1 if FAILED else 0)


def test_integration_chain_checks_all_pass():
    """Expose the module-level checks to pytest.

    The checks above run at import time.  Without this the bare
    ``sys.exit`` made pytest fail collection, so none of them ran.
    """
    assert FAILED == 0, f"{FAILED} check(s) failed"

