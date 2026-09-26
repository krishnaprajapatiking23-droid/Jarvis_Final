"""Canonical process observer (BUG 1).

The real implementation lives here; the legacy misspelled module is a thin
re-export wrapper. Works without psutil by reporting that process metrics
are unavailable instead of raising.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["ObserverResult", "Observer", "observer", "is_running"]

log = logging.getLogger(__name__)


@dataclass
class ObserverResult:
    """Outcome of one process lookup."""

    available: bool
    running: bool = False
    matches: List[str] = field(default_factory=list)
    error: str = ""

    def __bool__(self) -> bool:
        return self.running


class Observer:
    """Looks up running processes through psutil, with an OS fallback."""

    def __init__(self) -> None:
        self._psutil: Optional[Any] = None
        self._loaded = False
        self._load_error = ""

    def _load(self) -> bool:
        if self._loaded:
            return self._psutil is not None
        self._loaded = True
        try:
            import psutil
        except Exception as error:
            self._load_error = f"psutil unavailable: {type(error).__name__}"
            log.info(self._load_error)
            return False
        self._psutil = psutil
        return True

    @property
    def available(self) -> bool:
        return self._load() or bool(shutil.which("ps"))

    def status(self) -> Dict[str, Any]:
        """Report which backend can actually be used."""
        return {
            "psutil": self._load(),
            "ps_command": bool(shutil.which("ps")),
            "error": self._load_error,
        }

    def _names_from_psutil(self) -> List[str]:
        psutil = self._psutil
        names: List[str] = []
        for process in psutil.process_iter(["name"]):  # type: ignore[union-attr]
            try:
                names.append(process.info.get("name") or "")
            except Exception:
                continue
        return names

    def _names_from_ps(self) -> List[str]:
        try:
            finished = subprocess.run(
                ["ps", "-eo", "comm"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as error:
            log.debug("ps fallback failed: %r", error)
            return []
        return [line.strip() for line in finished.stdout.splitlines()[1:]]

    def find(self, process_name: str) -> ObserverResult:
        """Return every running process whose name contains ``process_name``."""
        needle = str(process_name or "").strip().lower()
        if not needle:
            return ObserverResult(True, error="process name is required")

        if self._load():
            names = self._names_from_psutil()
        elif shutil.which("ps"):
            names = self._names_from_ps()
        else:
            return ObserverResult(False, error=self._load_error or "no process API")

        matches = [name for name in names if needle in name.lower()]
        return ObserverResult(True, running=bool(matches), matches=matches)

    def is_running(self, process_name: str) -> bool:
        """Backwards-compatible boolean helper."""
        return self.find(process_name).running


observer = Observer()


def is_running(process_name: str) -> bool:
    """Module-level helper kept for existing callers."""
    return observer.is_running(process_name)
