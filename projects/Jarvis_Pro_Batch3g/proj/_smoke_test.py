"""Smoke test with hard wall-clock timeout per command.

Runs each command in a separate Python subprocess so a hung LLM call
cannot wedge the loop.  Each command gets its own 10-second budget.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PROJ = Path(r"C:\Users\Yogi\.minimax-agent\projects\Jarvis_Pro_Batch3g\proj")
PROBE = PROJ / "_probe_one.py"

# ---------------------------------------------------------------- probe script
PROBE.write_text(textwrap.dedent('''
    import json
    import sys
    import time
    sys.path.insert(0, r"{proj}")
    from brains_v2.manager import brain
    cmd = sys.argv[1]
    t0 = time.time()
    try:
        out = brain.process(cmd)
    except BaseException as exc:  # noqa: BLE001
        print(json.dumps({{"ok": False, "exc": f"{{type(exc).__name__}}: {{exc}}", "elapsed": time.time()-t0}}))
        sys.exit(2)
    dt = time.time() - t0
    if isinstance(out, dict):
        reply = out.get("reply", "")
        verif = out.get("verification") or {{}}
        ok = verif.get("success") if isinstance(verif, dict) else None
        print(json.dumps({{"ok": True, "elapsed": dt, "type": out.get("type"), "reply": str(reply)[:120],
                            "success": ok, "keys": sorted(out.keys())}}))
    else:
        print(json.dumps({{"ok": True, "elapsed": dt, "type": type(out).__name__, "value": str(out)[:120]}}))
''').format(proj=str(PROJ)), encoding="utf-8")

# ---------------------------------------------------------------- commands
COMMANDS: list[tuple[str, str]] = [
    ("conv.hello",        "hello"),
    ("conv.goodbye",      "goodbye"),
    ("conv.how_are_you",  "how are you"),
    ("conv.thanks",       "thanks"),
    ("conv.followup",     "and what about yesterday"),
    ("conv.incomplete",   "can you also"),
    ("conv.ref_it",       "close it"),
    ("note.add",          "add note buy groceries"),
    ("note.show",         "show notes"),
    ("note.read",         "read note 1"),
    ("rem.add",           "remind me at 9pm to call John"),
    ("rem.show",          "show reminders"),
    ("mem.remember",      "remember that I like pizza"),
    ("mem.recall",        "what do I like"),
    ("prof.python",       "I work with Python"),
    ("prof.switch_pro",   "switch to professional mode"),
    ("tool.calc",         "calculate 25 * 4"),
    ("tool.time",         "what time is it"),
    ("tool.date",         "what is today's date"),
    ("tool.trans",        "translate hello to spanish"),
    ("tool.weather",      "what is the weather in delhi"),
    ("tool.timer",        "set timer for 30 seconds"),
    ("tool.stopwatch",    "start stopwatch"),
    ("tool.joke",         "tell me a joke"),
    ("tool.wiki",         "who is Albert Einstein"),
    ("tool.calc2",        "what is 17% of 250"),
    ("brw.open_chrome",   "open chrome"),
    ("brw.search_google", "search google for weather today"),
    ("run_tests",         "run the test suite"),
    ("code.fibonacci",    "write a python function for fibonacci"),
    ("code.summarize",    "summarize this conversation"),
    ("wf.chain",          "open chrome then open youtube"),
    ("pers.mode_dev",     "switch to developer mode"),
]


def main() -> int:
    print(f"== Smoke-testing {len(COMMANDS)} commands (10s timeout each) ==", flush=True)
    failures = 0
    for label, cmd in COMMANDS:
        try:
            cp = subprocess.run(
                [sys.executable, "-u", str(PROBE), cmd],
                cwd=str(PROJ),
                capture_output=True,
                text=True,
                timeout=10,
            )
            stdout = cp.stdout.strip().splitlines()[-1] if cp.stdout else ""
            stderr = cp.stderr.strip()
            try:
                rec = json.loads(stdout)
            except Exception:
                rec = {"ok": False, "raw": stdout, "err": stderr[:200]}
        except subprocess.TimeoutExpired:
            rec = {"ok": False, "exc": "TIMEOUT>10s"}
        except Exception as exc:  # noqa: BLE001
            rec = {"ok": False, "exc": f"{type(exc).__name__}: {exc}"}

        if not rec.get("ok"):
            failures += 1
        flag = "OK" if rec.get("ok") else "FAIL"
        elapsed = rec.get("elapsed", 0)
        if "reply" in rec:
            print(f"[{label:18}] {cmd!r:42} [{flag} {elapsed:>5.2f}s] reply={rec['reply']!r:.70}  keys={rec.get('keys', [])[:6]}", flush=True)
        elif "value" in rec:
            print(f"[{label:18}] {cmd!r:42} [{flag} {elapsed:>5.2f}s] non-dict {rec['type']}={rec['value']!r:.70}", flush=True)
        else:
            print(f"[{label:18}] {cmd!r:42} [{flag} {elapsed:>5.2f}s] {rec.get('exc') or rec.get('err') or rec.get('raw')}", flush=True)

    print(f"\n== Done.  {failures}/{len(COMMANDS)} failed ==", flush=True)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
