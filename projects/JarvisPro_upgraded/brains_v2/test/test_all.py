"""Run every brains_v2 smoke test in one go."""

from __future__ import annotations

import importlib
import traceback
from typing import List, Tuple

MODULES = ("test_memory", "test_agents", "test_desktop",
           "test_mobile", "test_server", "test_voice")


def run_all() -> Tuple[int, List[str]]:
    passed = 0
    failures: List[str] = []

    for name in MODULES:
        try:
            module = importlib.import_module("brains_v2.test." + name)
            getattr(module, name)()
            passed += 1
        except Exception as error:
            failures.append("%s: %s: %s" % (name, type(error).__name__, error))
            traceback.print_exc()

    return passed, failures


def test_all() -> None:
    passed, failures = run_all()
    assert not failures, "; ".join(failures)
    assert passed == len(MODULES)


if __name__ == "__main__":
    count, problems = run_all()
    print("%d/%d passed" % (count, len(MODULES)))
    for problem in problems:
        print("  FAIL", problem)
