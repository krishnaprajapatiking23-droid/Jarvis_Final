"""Final verification — test all fixed/bUILT modules import cleanly."""
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Yogi\.minimax-agent\projects\Jarvis_Pro_Batch3g\proj")
sys.path.insert(0, str(ROOT))

MODULES = [
    ("brains_v2.manager",         "brains_v2/manager.py"),
    ("brains_v2.decision",        "brains_v2/decision.py"),
    ("brains_v2.decision_tree",   "brains_v2/decision_tree.py"),
    ("brains_v2.self_correction",  "brains_v2/self_correction.py"),
    ("brains_v2.self_improvement", "brains_v2/self_improvement.py"),
    ("business.business",          "business/business.py"),
    ("vision.vision_engine",       "vision/vision_engine.py"),
    ("learning.manager",            "learning/manager.py"),
    ("computer_automation.manager", "computer_automation/manager.py"),
    ("testing.manager",             "testing/manager.py"),
    ("event_bus.bus",               "event_bus/bus.py"),
    ("workflow.manager",             "workflow/manager.py"),
    ("android.manager",              "android/manager.py"),
    ("backup.manager",               "backup/manager.py"),
    ("smarthome.manager",           "smarthome/manager.py"),
    ("desktop_ui.manager",           "desktop_ui/manager.py"),
    ("analytics.engine",            "analytics/engine.py"),
    ("developer.manager",           "developer/manager.py"),
    ("reliability.manager",         "reliability/manager.py"),
    ("browser.manager",             "browser/manager.py"),
    ("research.manager",            "research/manager.py"),
]

passed = failed = 0
for module, path in MODULES:
    full = ROOT / path
    if not full.exists():
        print(f"  [MISSING] {module} ({path})")
        failed += 1
        continue
    try:
        __import__(module)
        print(f"  [  OK   ] {module}")
        passed += 1
    except Exception as e:
        print(f"  [FAILED ] {module}: {e}")
        failed += 1

print(f"\n{'='*50}")
print(f"  PASSED: {passed}/{len(MODULES)}")
print(f"  FAILED: {failed}/{len(MODULES)}")
sys.exit(0 if failed == 0 else 1)
