"""Stdlib test runner for JARVIS PRO.

pytest is the preferred runner (``python -m pytest -q``). This script exists so
the suite can also be executed in environments where pytest is not installed:
it collects ``unittest.TestCase`` classes *and* bare ``test_*`` functions that
use plain ``assert``, which covers the way tests are written in this repo.

    python run_agi_tests.py              # AGI tests only
    python run_agi_tests.py --all        # every test under tests/
    python run_agi_tests.py -v           # verbose
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import os
import sys
import time
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Skip(Exception):
    """Raised by a test to report that it cannot run in this environment."""


def _load(path: Path):
    name = "jt_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    return module


def _run_function(fn) -> tuple[str, str]:
    """Run one bare test function. Returns (outcome, detail)."""

    if inspect.signature(fn).parameters:
        return "skip", "requires fixtures"

    try:
        fn()

    except Skip as exc:
        return "skip", str(exc)

    except unittest.SkipTest as exc:
        return "skip", str(exc)

    except AssertionError:
        return "fail", traceback.format_exc(limit=6)

    except Exception:
        return "fail", traceback.format_exc(limit=6)

    return "pass", ""


def collect(paths: list[Path], verbose: bool = False) -> dict:
    passed: list[str] = []
    failed: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    load_errors: list[tuple[str, str]] = []

    for path in sorted(paths):
        try:
            module = _load(path)

        except Exception:
            load_errors.append((path.name, traceback.format_exc(limit=4)))
            continue

        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        functions = []

        for name, obj in vars(module).items():
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                if obj.__module__ == module.__name__:
                    suite.addTests(loader.loadTestsFromTestCase(obj))

            elif name.startswith("test_") and inspect.isfunction(obj):
                if obj.__module__ == module.__name__:
                    functions.append((name, obj))

        if suite.countTestCases():
            stream = open(os.devnull, "w", encoding="utf-8")

            try:
                result = unittest.TextTestRunner(
                    stream=stream, verbosity=0
                ).run(suite)

            finally:
                stream.close()

            bad = {str(t) for t, _ in result.failures + result.errors}
            skips = {str(t): r for t, r in result.skipped}

            for test, detail in result.failures + result.errors:
                failed.append((f"{path.name}::{test}", detail))

            for test, reason in result.skipped:
                skipped.append((f"{path.name}::{test}", reason))

            total = result.testsRun - len(bad) - len(skips)
            passed.extend([f"{path.name}::case{i}" for i in range(total)])

        for name, fn in functions:
            outcome, detail = _run_function(fn)
            label = f"{path.name}::{name}"

            if outcome == "pass":
                passed.append(label)

                if verbose:
                    print(f"  PASS {label}")

            elif outcome == "skip":
                skipped.append((label, detail))

                if verbose:
                    print(f"  SKIP {label}: {detail}")

            else:
                failed.append((label, detail))
                print(f"  FAIL {label}")

    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "load_errors": load_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="run every test")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--pattern", default="")
    args = parser.parse_args()

    tests_dir = ROOT / "tests"

    if args.pattern:
        paths = list(tests_dir.glob(f"test_*{args.pattern}*.py"))

    elif args.all:
        paths = list(tests_dir.glob("test_*.py"))

    else:
        paths = list(tests_dir.glob("test_agi_*.py"))

    if not paths:
        print("no test files matched")
        return 1

    started = time.monotonic()
    report = collect(paths, verbose=args.verbose)
    elapsed = time.monotonic() - started

    for name, detail in report["load_errors"]:
        print(f"\nLOAD ERROR {name}\n{detail}")

    for name, detail in report["failed"]:
        print(f"\n{name}\n{detail}")

    print(
        f"\n{len(report['passed'])} passed, "
        f"{len(report['failed'])} failed, "
        f"{len(report['skipped'])} skipped, "
        f"{len(report['load_errors'])} load errors "
        f"in {elapsed:.2f}s"
    )

    return 1 if report["failed"] or report["load_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
