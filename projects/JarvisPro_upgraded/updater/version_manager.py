"""
Version Manager — Tracks and compares JarvisPro versions.
"""
import os
import re
import json
from pathlib import Path
from typing import Optional, Tuple

JARVIS_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = JARVIS_ROOT / "version.txt"


class VersionManager:
    """Manages JarvisPro version detection and comparison."""

    def __init__(self):
        self._current: Optional[Tuple[int, int, int]] = None
        self._version_string: Optional[str] = None

    # ------------------------------------------------------------------ #
    #  Detection                                                          #
    # ------------------------------------------------------------------ #
    def get_current_version(self) -> Tuple[int, int, int]:
        """Return current version as (major, minor, patch)."""
        if self._current is not None:
            return self._current
        self._current = self._parse_file()
        return self._current

    def get_version_string(self) -> str:
        """Return current version as a human-readable string."""
        if self._version_string is not None:
            return self._version_string
        major, minor, patch = self.get_current_version()
        self._version_string = f"{major}.{minor}.{patch}"
        return self._version_string

    def _parse_file(self) -> Tuple[int, int, int]:
        """Read version.txt and parse 'X.Y.Z' or 'X.Y' or 'X'."""
        if not VERSION_FILE.exists():
            return (1, 0, 0)
        try:
            content = VERSION_FILE.read_text(encoding="utf-8").strip()
            match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", content)
            if not match:
                return (1, 0, 0)
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else 0
            patch = int(match.group(3)) if match.group(3) else 0
            return (major, minor, patch)
        except Exception:
            return (1, 0, 0)

    # ------------------------------------------------------------------ #
    #  Comparison                                                         #
    # ------------------------------------------------------------------ #
    def is_newer(self, other: str) -> bool:
        """Return True if other version is strictly newer than current."""
        other_tuple = self._parse_version_string(other)
        return other_tuple > self.get_current_version()

    def needs_update(self, remote: str) -> bool:
        """Alias for is_newer."""
        return self.is_newer(remote)

    @staticmethod
    def _parse_version_string(version: str) -> Tuple[int, int, int]:
        """Parse any 'X.Y.Z' version string into a comparable tuple."""
        match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
        if not match:
            return (0, 0, 0)
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        patch = int(match.group(3)) if match.group(3) else 0
        return (major, minor, patch)

    @staticmethod
    def compare(v1: str, v2: str) -> int:
        """
        Compare two version strings.
        Returns: -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        t1 = VersionManager._parse_version_string(v1)
        t2 = VersionManager._parse_version_string(v2)
        if t1 < t2:
            return -1
        if t1 > t2:
            return 1
        return 0

    # ------------------------------------------------------------------ #
    #  Manifest helpers                                                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_manifest(
        version: str,
        changelog: str = "",
        min_python: str = "3.8",
        min_os: str = "Windows 10",
        download_url: str = "",
        sha256: str = "",
        size_bytes: int = 0,
    ) -> dict:
        """Build a release manifest dictionary."""
        return {
            "version": version,
            "changelog": changelog,
            "requirements": {
                "python": min_python,
                "os": min_os,
            },
            "download": {
                "url": download_url,
                "sha256": sha256,
                "size_bytes": size_bytes,
            },
            "released_at": "",
        }

    def format_manifest_summary(self, manifest: dict) -> str:
        """Format a manifest dict into a human-readable string."""
        v = manifest.get("version", "unknown")
        changelog = manifest.get("changelog", "")
        reqs = manifest.get("requirements", {})
        dl = manifest.get("download", {})
        size_kb = (dl.get("size_bytes", 0) or 0) // 1024
        lines = [
            f"Version: {v}",
            f"Python: >= {reqs.get('python', '?')}",
            f"OS: {reqs.get('os', '?')}",
            f"Size: {size_kb} KB" if size_kb else "",
        ]
        if changelog:
            lines.append(f"Changelog:\n{changelog}")
        return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------- #
#  Singleton                                                             #
# ---------------------------------------------------------------------- #
_version_manager: Optional[VersionManager] = None


def get_version_manager() -> VersionManager:
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
