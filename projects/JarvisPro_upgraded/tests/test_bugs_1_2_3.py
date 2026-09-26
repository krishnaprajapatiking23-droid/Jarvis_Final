"""Regression evidence for the three deep-repair bugs, with the kernel wired in.

Run: python3 tests/test_bugs_1_2_3.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brains_v2.runtime import GREETING, JarvisRuntime, brain_call  # noqa: E402

FAILED = []


def check(name, cond, evidence=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {evidence}")
    if not cond:
        FAILED.append(name)


class FakeBrain:
    """Stands in for BrainV2: exposes the canonical process() only."""

    def __init__(self):
        self.seen = []

    def process(self, text):
        self.seen.append(text)
        return f"handled {text}"


class FakePipeline:
    def __init__(self):
        self.brain = None
        self.turns = []
        self.dropped_turns = 0

    def attach_brain(self, brain):
        self.brain = brain

    def handle_text(self, text):
        if self.brain is None:
            self.dropped_turns += 1
            return None
        if text.strip().lower() in {"goodbye", "exit", "quit"}:
            return "Goodbye."
        reply = brain_call(self.brain, text)
        self.turns.append((text, reply))
        return reply


def main() -> int:
    import tempfile

    from jarvis_core.kernel import Kernel

    brain = FakeBrain()
    pipe = FakePipeline()
    rt = JarvisRuntime(brain_factory=lambda: brain, pipeline_factory=lambda: pipe)
    # isolate kernel state so this regression test never reads the live databases
    rt._kernel = Kernel(data_dir=tempfile.mkdtemp(prefix="jarvis_bugtest_"))

    # BUG 3 - startup reporting
    report = rt.start(announce=False)
    check("BUG 3 startup greeting present", GREETING in report.greeting, report.greeting)
    check("BUG 3 status is reported", report.status in ("ONLINE", "DEGRADED"), f"status {report.status}")
    check("BUG 3 per-service report", [s.name for s in report.services][:4]
          == ["storage", "scheduler", "brain", "pipeline"],
          " | ".join(report.lines()))
    check("BUG 3 kernel reported at startup",
          any(s.name == "kernel" and s.status == "ok" for s in report.services), "kernel ok")

    # BUG 1 - one brain, injected
    check("BUG 1 same brain injected into pipeline", pipe.brain is brain and rt.brain() is brain,
          f"same brain: {pipe.brain is rt.brain()}")
    check("BUG 1 pipeline reports attachment", pipe.brain is not None, "attached: True True")

    # BUG 2 - canonical process(), real replies
    session = ["Hello", "Open calculator", "What is 2 + 2?", "Remember this", "Show my reminders"]
    replies = [pipe.handle_text(t) for t in session]
    check("BUG 2 every turn got a real reply", all(r and r.startswith("handled") for r in replies),
          replies[0])
    check("BUG 2 canonical process() used", brain.seen == session, f"{len(brain.seen)} turns via process()")
    check("BUG 1 no dropped turns", pipe.dropped_turns == 0, f"dropped_turns: {pipe.dropped_turns}")
    check("BUG 2 exit phrase still works", pipe.handle_text("Goodbye") == "Goodbye.", "Goodbye.")

    # kernel integration through the canonical entry point
    out = rt.process("Open calculator")
    trace = rt.last_trace()
    chain = rt.kernel().observability.chain(trace)
    check("kernel traces the real request", out == "handled Open calculator"
          and trace.startswith("JRV-") and chain == ["input", "manager", "output"],
          f"{trace}: {' -> '.join(chain)}")
    check("kernel records analytics for the request",
          rt.kernel().analytics.success_rate("command") == 1.0, "success_rate 1.0")

    print(f"\n{'ALL PASS' if not FAILED else 'FAILURES: ' + str(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
