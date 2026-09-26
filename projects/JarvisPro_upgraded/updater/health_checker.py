"""
Health Checker — Verifies that JarvisPro is in a good state after updates.
"""
import sys
import time
import importlib
from pathlib import Path
from typing import Dict, List, Optional, Any

JARVIS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JARVIS_ROOT))

from .version_manager import get_version_manager  # noqa: E402


class HealthChecker:
    """
    Runs a battery of health checks on the JarvisPro installation.
    Each check returns (passed: bool, detail: str).
    """

    CRITICAL_IMPORTS = [
        ("jarvis_core", "jarvis_core"),
        ("core.event_bus", "core.event_bus"),
        ("core.router", "core.router"),
        ("brains_v2.runtime", "brains_v2.runtime"),
        ("brains_v2.core_bridge", "brains_v2.core_bridge"),
        ("jarvis_core.kernel", "jarvis_core.kernel"),
    ]

    def __init__(self):
        self._last_result: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #
    def check(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Run all health checks and return a summary dict.

        Returns:
            {
                "healthy": bool,
                "score": int,          # 0-100
                "checks": [...],
                "error": str | None,
                "runtime_version": str,
                "checked_at": str,
            }
        """
        results: List[Dict[str, Any]] = []
        passed = 0

        # Core imports
        for display_name, module_path in self.CRITICAL_IMPORTS:
            ok, detail = self._check_import(module_path)
            results.append({"check": f"import:{display_name}", "passed": ok, "detail": detail})
            if ok:
                passed += 1

        # Core files
        critical_files = [
            "jarvis.py",
            "requirements.txt",
            "version.txt",
        ]
        for fname in critical_files:
            ok, detail = self._check_file(JARVIS_ROOT / fname)
            results.append({"check": f"file:{fname}", "passed": ok, "detail": detail})
            if ok:
                passed += 1

        # Config
        ok, detail = self._check_config()
        results.append({"check": "config", "passed": ok, "detail": detail})
        if ok:
            passed += 1

        total = len(results)
        score = int(100 * passed / max(total, 1))
        healthy = score >= 80  # 80% threshold

        self._last_result = {
            "healthy": healthy,
            "score": score,
            "checks": results,
            "passed": passed,
            "total": total,
            "error": None,
            "runtime_version": self._get_runtime_version(),
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self._last_result

    def quick_check(self) -> bool:
        """True if the most critical imports are loadable."""
        for _, module_path in self.CRITICAL_IMPORTS[:3]:
            ok, _ = self._check_import(module_path)
            if not ok:
                return False
        return True

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        return self._last_result

    # ------------------------------------------------------------------ #
    #  Individual checks                                                  #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _check_import(module_path: str) -> tuple:
        """Try importing a module. Returns (success, detail)."""
        try:
            mod = importlib.import_module(module_path)
            version = getattr(mod, "__version__", "unknown")
            return True, f"OK — {module_path} (v{version})"
        except ImportError as e:
            return False, f"ImportError: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    @staticmethod
    def _check_file(path: Path) -> tuple:
        """Check if a required file exists and is readable."""
        if not path.exists():
            return False, f"Missing: {path.name}"
        if not path.is_file():
            return False, f"Not a file: {path.name}"
        try:
            path.read_bytes()[:1]  # read 1 byte to verify readable
            return True, f"OK — {path.name} ({path.stat().st_size} bytes)"
        except Exception as e:
            return False, f"Cannot read {path.name}: {e}"

    @staticmethod
    def _check_config() -> tuple:
        """Check that config files are present and readable."""
        env_file = JARVIS_ROOT / ".env"
        config_file = JARVIS_ROOT / "config.py"
        if env_file.exists() or config_file.exists():
            return True, "Config files present"
        return True, "No config files (may be first run)"

    @staticmethod
    def _get_runtime_version() -> str:
        try:
            vm = get_version_manager()
            return vm.get_version_string()
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------ #
    #  Formatting                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_result(result: Dict[str, Any]) -> str:
        """Format a health check result dict as a readable string."""
        if not result:
            return "No health check result available."
        lines = [
            f"JarvisPro Health Check — {result.get('checked_at', '')}",
            f"{'=' * 50}",
            f"Status: {'✅ HEALTHY' if result.get('healthy') else '❌ UNHEALTHY'}",
            f"Score: {result.get('score', 0)}/100",
            f"Passed: {result.get('passed', 0)}/{result.get('total', 0)}",
            f"Version: {result.get('runtime_version', 'unknown')}",
            "",
            "Checks:",
        ]
        for chk in result.get("checks", []):
            icon = "✅" if chk["passed"] else "❌"
            lines.append(f"  {icon} {chk['check']}: {chk['detail']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------- #
#  Singleton                                                             #
# ---------------------------------------------------------------------- #
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
