"""
Testing Manager — runs unit tests against JARVIS modules and reports results.
"""

import time
import traceback
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List


TestFunc = Callable[[], Dict]


class TestManager:

    def __init__(self):
        self._suites: Dict[str, List[TestFunc]] = {}
        self._results: List[Dict] = []
        self._lock = Lock()

    def register(self, suite_name: str, test_func: TestFunc) -> None:
        """Register a test function under a named suite."""
        if suite_name not in self._suites:
            self._suites[suite_name] = []
        self._suites[suite_name].append(test_func)

    def run(self, suite_name: str = None) -> Dict:
        """Run all tests in a suite, or all suites if no name given."""
        results = []
        suites_to_run = (
            {suite_name: self._suites[suite_name]}
            if suite_name and suite_name in self._suites
            else self._suites
        )

        for name, funcs in suites_to_run.items():
            for test in funcs:
                started = time.time()
                try:
                    outcome = test()
                    elapsed = round(time.time() - started, 4)
                    results.append({
                        "suite": name,
                        "name": test.__name__,
                        "status": "PASS" if outcome.get("passed", False) else "FAIL",
                        "elapsed_s": elapsed,
                        "detail": outcome.get("detail", ""),
                    })
                except Exception:
                    elapsed = round(time.time() - started, 4)
                    results.append({
                        "suite": name,
                        "name": test.__name__,
                        "status": "ERROR",
                        "elapsed_s": elapsed,
                        "detail": traceback.format_exc()[-300:],
                    })

        with self._lock:
            self._results = results

        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(results), 3) if results else 0.0,
            "results": results,
        }

    def report(self) -> Dict:
        return {
            "total_runs": len(self._results),
            "passed": sum(1 for r in self._results if r["status"] == "PASS"),
            "failed": sum(1 for r in self._results
                          if r["status"] in ("FAIL", "ERROR")),
            "results": self._results,
        }


_manager = TestManager()

register = _manager.register
run = _manager.run
report = _manager.report
