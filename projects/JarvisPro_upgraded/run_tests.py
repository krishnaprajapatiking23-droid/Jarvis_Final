"""Offline test runner (Phase 16).

This sandbox has no network, so ``pip install pytest`` is impossible. This
runner uses only the standard library and collects exactly what pytest would
collect per ``pytest.ini``: every ``tests/test_*.py`` module. Interactive
demonstration scripts live in ``manual_demos/`` and are never collected, so
the suite cannot hang on ``input()``.

Usage:
    python3 run_tests.py            # whole suite
    python3 run_tests.py deep_repair  # substring filter on module names
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "tests"


def _load(path: Path) -> unittest.TestSuite:
    """Import a test module by path without needing a package __init__."""
    name = "jarvis_tests_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    # Several suites are written pytest-style: module-level test_*
    # functions with no TestCase class. Collect those as well, so no test
    # is silently hidden from the run.
    for attribute in sorted(vars(module)):
        if not attribute.startswith("test_"):
            continue
        candidate = getattr(module, attribute)
        if not callable(candidate):
            continue
        if getattr(candidate, "__module__", "") != name:
            continue
        try:
            arity = candidate.__code__.co_argcount
        except AttributeError:
            continue
        if arity != 0:
            continue  # fixtures are not supported by the offline runner
        suite.addTest(unittest.FunctionTestCase(candidate))
    return suite


def main(argv: List[str]) -> int:
    os.environ.setdefault("JARVIS_TESTING", "1")
    sys.path.insert(0, str(ROOT))

    patterns = [value for value in argv if not value.startswith("-")]
    files = sorted(TESTS.glob("test_*.py"))
    if patterns:
        files = [
            path for path in files if any(pattern in path.stem for pattern in patterns)
        ]

    suite = unittest.TestSuite()
    loaded = 0
    for path in files:
        try:
            suite.addTest(_load(path))
            loaded += 1
        except Exception as error:
            print(f"ERROR: could not import {path.name}: {error!r}")
            return 2

    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    print(
        "files=%d collected=%d failed=%d errors=%d skipped=%d"
        % (
            loaded,
            result.testsRun,
            len(result.failures),
            len(result.errors),
            len(result.skipped),
        )
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
