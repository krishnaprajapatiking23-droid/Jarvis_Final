"""Tiny test runner for environments without pytest installed.

Usage::

    python tools/run_tests.py                      # every file in tests/
    python tools/run_tests.py tests/test_x.py ...  # specific files

It imports each file and calls every module level ``test_*`` function, so the
test files stay plain pytest files (``python -m pytest`` works too).

Files that cannot be imported because an optional dependency is missing
(for example ``ollama`` on a machine without the model runtime) are
reported as skipped rather than failed.
"""

import glob
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def discover():
    """Every test file in the tests/ directory, sorted."""

    pattern = os.path.join(ROOT, "tests", "test_*.py")
    return sorted(glob.glob(pattern))


def load(path):
    """Import a test file by path."""

    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_file(path):
    """Run every ``test_*`` function in one file.

    Returns ``(passed, failed, skipped)``.
    """

    print(f"\n===== {path} =====")
    try:
        module = load(path)
    except ImportError as error:
        print(f"SKIP FILE (optional dependency missing: {error})")
        return 0, 0, 1
    except Exception:
        print("IMPORT FAILED")
        traceback.print_exc()
        return 0, 1, 0

    passed = 0
    failed = 0
    skipped = 0

    for name in sorted(vars(module)):
        if not name.startswith("test_"):
            continue
        function = getattr(module, name)
        if not callable(function):
            continue
        if function.__code__.co_argcount:
            print(f"SKIP {name} (needs pytest fixtures)")
            skipped += 1
            continue
        try:
            function()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc(limit=4)
        else:
            passed += 1
            print(f"PASS {name}")

    return passed, failed, skipped


def main(argv):
    files = argv or discover()
    if not files:
        print("no test files found")
        return 0

    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for path in files:
        full = path if os.path.isabs(path) else os.path.join(ROOT, path)
        passed, failed, skipped = run_file(full)
        total_passed += passed
        total_failed += failed
        total_skipped += skipped

    print(
        f"\nTOTAL passed={total_passed} "
        f"failed={total_failed} skipped={total_skipped}"
    )
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
