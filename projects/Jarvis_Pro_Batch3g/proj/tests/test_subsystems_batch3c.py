"""Behavioural tests for Batch 3c: S20 self-correction, S21 self-improvement.

Real telemetry in, real proposals out, real file edits with real regression
subprocesses and real rollback. No mocked results.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.analytics import Analytics
from jarvis_core.learning import ExperienceDB, LearningEngine
from jarvis_core.self_improvement import (APPLIED, BLOCKED, REJECTED, RISK_HIGH,
                                          ROLLED_BACK, SelfImprovementEngine)

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


TMP = tempfile.mkdtemp(prefix="jarvis_b3c_")
PROJ = os.path.join(TMP, "proj")
os.makedirs(os.path.join(PROJ, "tests"), exist_ok=True)

analytics = Analytics(os.path.join(TMP, "analytics.db"))
learning = LearningEngine(ExperienceDB(os.path.join(TMP, "experience.db")))
engine = SelfImprovementEngine(os.path.join(TMP, "improvement.db"),
                               learning=learning, analytics=analytics,
                               project_root=PROJ)

print("\n=== S20 save successful correction ===")
unverified = engine.save_correction("browser upload fails", "selector changed",
                                    "use the accessibility id instead")
check("an unverified correction is refused, never learned",
      unverified["status"] == "rejected", unverified["error"])

no_test = engine.save_correction("browser upload fails", "selector changed",
                                 "use the accessibility id", verified=True)
check("a correction without a named test is refused",
      no_test["status"] == "rejected", no_test["error"])

bad_input = engine.save_correction("", "cause", "fix", verified=True, test="t")
check("corrections validate their input",
      bad_input["status"] == "invalid_input", bad_input["error"])

saved = engine.save_correction(
    "browser upload fails with stale selector",
    "the page renamed #file to #attachment",
    "look the input up by accessibility label before falling back to css",
    test="tests/test_subsystems_batch3.py::upload",
    result="upload verified, attachment=payload.bin",
    verified=True, trace_id="JRV-2026-00000101")
check("a verified correction is stored with problem/cause/correction/test/result",
      saved["status"] == "ok" and saved["id"].startswith("CX-"),
      f"id={saved['id']}")
check("the correction is also written to the experience store for reuse",
      saved["experience_id"] is not None,
      f"experience_id={saved['experience_id']}")

stored = engine.corrections()[0]
check("the stored record keeps its test evidence",
      stored["test"].endswith("::upload") and stored["verified"],
      f"test={stored['test']}")

reuse = engine.find_correction("upload fails stale selector on browser")
check("a similar problem reuses the previously verified correction",
      reuse is not None and reuse["id"] == saved["id"],
      f"match={reuse['match'] if reuse else None}")
check("reuse is counted so useless corrections can be spotted",
      engine.corrections()[0]["reuses"] == 1,
      f"reuses={engine.corrections()[0]['reuses']}")
check("an unrelated problem does not match a stored correction",
      engine.find_correction("smart light stopped responding") is None,
      "no false reuse")

print("\n=== S21 improvement generation from real telemetry ===")
clean = engine.generate_improvements()
check("with healthy telemetry no improvements are invented", clean == [],
      f"{len(clean)} proposals")

for i in range(5):
    analytics.record("manager", "flaky_manager", success=(i == 0))
for i in range(4):
    analytics.record("manager", "good_manager", success=True)
analytics.record("tool", "slow_tool", success=True, duration_ms=9000)
analytics.record("tool", "slow_tool", success=True, duration_ms=8000)
analytics.record("tool", "slow_tool", success=True, duration_ms=7000)
for _ in range(3):
    learning.learn_error("opening a file", "open path", "PermissionError: denied")

obs = engine.observe()
check("observation is built from analytics and experience, not guesses",
      set(obs["source"]) == {"analytics", "experience"} and obs["managers"],
      f"sources={obs['source']} managers={len(obs['managers'])}")

weak = engine.identify_weaknesses(obs)
kinds = sorted({w["kind"] for w in weak})
check("real weaknesses are detected from telemetry",
      "low_success_rate" in kinds and "slow_operation" in kinds
      and "repeated_error" in kinds, f"kinds={kinds}")
check("a healthy manager is not flagged",
      all(w["target"] != "good_manager" for w in weak),
      "good_manager (100% of 4 runs) not flagged")
low = [w for w in weak if w["kind"] == "low_success_rate"][0]
check("weaknesses carry numeric evidence",
      low["evidence"]["samples"] == 5 and low["evidence"]["success_rate"] == 0.2,
      f"{low['detail']}")

proposals = engine.generate_improvements(obs)
check("every weakness produces a proposal with rationale and risk",
      len(proposals) == len(weak)
      and all(p["proposal"] and p["rationale"] and p["risk"] for p in proposals),
      f"{len(proposals)} proposals, risks={sorted({p['risk'] for p in proposals})}")
check("proposals are persisted as history",
      len(engine.history()) == len(proposals), f"{len(engine.history())} in history")

print("\n=== S21 safe application, regression and rollback ===")
target_rel = "module_under_change.py"
target = os.path.join(PROJ, target_rel)
with open(target, "w", encoding="utf-8") as fh:
    fh.write("VALUE = 1\n")
ORIGINAL = open(target, encoding="utf-8").read()

good_suite = os.path.join(PROJ, "tests", "suite_ok.py")
with open(good_suite, "w", encoding="utf-8") as fh:
    fh.write("import sys, os\n"
             "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
             "import module_under_change as m\n"
             "assert m.VALUE == 2, f'VALUE={m.VALUE}'\n"
             "print('1 passed, 0 failed')\n")
bad_suite = os.path.join(PROJ, "tests", "suite_strict.py")
with open(bad_suite, "w", encoding="utf-8") as fh:
    fh.write("import sys, os\n"
             "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
             "import module_under_change as m\n"
             "assert m.VALUE == 1, f'regression: VALUE={m.VALUE}'\n"
             "print('1 passed, 0 failed')\n")


def bump(path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("VALUE = 2\n")


imp_id = proposals[0]["id"]
no_tests = engine.apply_improvement(imp_id, target_file=target_rel, change=bump)
check("an improvement cannot be applied without regression tests",
      no_tests["status"] == "invalid_input"
      and open(target, encoding="utf-8").read() == ORIGINAL, no_tests["error"])
check("the blocked improvement is recorded as blocked",
      engine.get_improvement(imp_id)["status"] == BLOCKED, "status=blocked")

escape = engine.apply_improvement(imp_id, target_file="../../etc/hosts",
                                  change=bump,
                                  regression_suites=["tests/suite_ok.py"])
check("path traversal outside the project root is refused",
      escape["status"] == "permission_denied", escape["error"])

os.makedirs(os.path.join(PROJ, "jarvis_core"), exist_ok=True)
with open(os.path.join(PROJ, "jarvis_core", "kernel.py"), "w", encoding="utf-8") as fh:
    fh.write("# critical file\n")
high = engine.apply_improvement(imp_id, target_file="jarvis_core/kernel.py",
                                change=bump,
                                regression_suites=["tests/suite_ok.py"])
check("high-risk targets require explicit approval",
      high["status"] == "permission_denied" and high["risk"] == RISK_HIGH,
      high["error"])

regression = engine.run_regression(["tests/suite_strict.py"], improvement_id=imp_id)
check("regression suites are really executed in a subprocess",
      regression["ok"] and regression["passed"] == 1,
      f"detail={regression['suites'][0]['detail'][:40]}")

missing = engine.run_regression(["tests/does_not_exist.py"], improvement_id=imp_id)
check("a missing suite is unavailable, never a silent pass",
      not missing["ok"] and missing["suites"][0]["status"] == "unavailable",
      missing["suites"][0]["detail"])

empty = engine.run_regression([])
check("applying with an empty suite list verifies nothing",
      not empty["ok"] and empty["status"] == "invalid_input", empty["error"])

rolled = engine.apply_improvement(imp_id, target_file=target_rel, change=bump,
                                  regression_suites=["tests/suite_strict.py"])
check("a failing regression rolls the change back from a real backup",
      rolled["status"] == "rolled_back"
      and open(target, encoding="utf-8").read() == ORIGINAL,
      f"status={rolled['status']} file={open(target, encoding='utf-8').read().strip()}")
check("the rollback is visible in improvement history",
      engine.get_improvement(imp_id)["status"] == ROLLED_BACK,
      f"status={engine.get_improvement(imp_id)['status']}")

accepted = engine.apply_improvement(imp_id, target_file=target_rel, change=bump,
                                    regression_suites=["tests/suite_ok.py"])
check("an improvement whose regression passes is accepted and kept",
      accepted["status"] == "ok" and accepted["accepted"]
      and open(target, encoding="utf-8").read().strip() == "VALUE = 2",
      f"status={accepted['status']} file={open(target, encoding='utf-8').read().strip()}")
check("accepted improvements are marked applied",
      engine.get_improvement(imp_id)["status"] == APPLIED,
      f"status={engine.get_improvement(imp_id)['status']}")


def broken(path):
    raise RuntimeError("patch generator produced invalid code")


crash = engine.apply_improvement(proposals[1]["id"], target_file=target_rel,
                                 change=broken,
                                 regression_suites=["tests/suite_ok.py"])
check("a change that raises is rolled back and reported",
      crash["status"] == "failure" and crash["rolled_back"]
      and open(target, encoding="utf-8").read().strip() == "VALUE = 2",
      crash["error"])

rej = engine.reject(proposals[2]["id"], "not worth the churn")
check("an improvement can be rejected with a reason",
      rej["state"] == REJECTED
      and engine.get_improvement(proposals[2]["id"])["status"] == REJECTED,
      rej["reason"])
check("unknown improvement ids are rejected as invalid input",
      engine.reject("IMP-nope", "x")["status"] == "invalid_input",
      "unknown id handled")

hist = [h for h in engine.history() if h["id"] == imp_id][0]
phases = [r["phase"] for r in hist["runs"]]
check("improvement history records every phase with evidence",
      "backup" in phases and "apply" in phases and "regression" in phases
      and "rollback" in phases, f"phases={sorted(set(phases))}")

backups = os.listdir(engine.backup_dir)
check("backups are real files on disk", any(b.endswith(".bak") for b in backups),
      f"{len(backups)} backup file(s)")

engine2 = SelfImprovementEngine(os.path.join(TMP, "improvement.db"),
                                learning=learning, analytics=analytics,
                                project_root=PROJ)
check("improvement and correction history survive restart",
      len(engine2.history()) == len(engine.history())
      and engine2.stats()["corrections"] == 1,
      f"{len(engine2.history())} improvements, {engine2.stats()['corrections']} corrections")

bad_action = engine.run("rewrite_everything")
check("unknown self-improvement actions are invalid input",
      bad_action["status"] == "invalid_input", bad_action["error"])

print("\n=== kernel integration ===")
from jarvis_core.kernel import Kernel  # noqa: E402

kdir = os.path.join(TMP, "kdata")
os.makedirs(kdir, exist_ok=True)
k = Kernel(data_dir=kdir)
check("the kernel owns a learning engine and a self-improvement engine",
      hasattr(k, "learning") and hasattr(k, "improvement"),
      "kernel.learning and kernel.improvement present")
sel = k.managers.select("self_improvement")
check("self-improvement is selectable through the manager registry",
      sel["manager"] == "self_improvement", f"status={sel['status']}")
kc = k.improvement.save_correction(
    "pipeline lost the brain", "no dependency injection in the pipeline",
    "inject BrainV2 from Application into the pipeline",
    test="tests/test_bugs_1_2_3.py", result="ALL PASS", verified=True)
check("corrections can be saved through the live kernel",
      kc["status"] == "ok", f"id={kc['id']}")
kh = k.health()
check("kernel health reports learning and improvement state",
      kh["improvement"]["available"] and "corrections" in kh["improvement"],
      f"corrections={kh['improvement']['corrections']}")
k.agents.shutdown()

print(f"\n{PASS} passed, {FAIL} failed")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
