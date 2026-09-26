"""
Update Checker — Fetches remote release info from GitHub releases.
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .version_manager import VersionManager, get_version_manager


class UpdateChecker:
    """
    Checks GitHub releases for a newer JarvisPro version.
    Falls back gracefully when no internet / no token / rate-limited.
    """

    DEFAULT_BASE_URL = "https://api.github.com/repos"
    DEFAULT_TIMEOUT = 10  # seconds

    def __init__(
        self,
        owner: str = "YOUR_USERNAME",
        repo: str = "JarvisPro",
        branch: str = "main",
        version_manager: Optional[VersionManager] = None,
    ):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self._vm = version_manager or get_version_manager()
        self._last_check: Optional[float] = None
        self._cached_manifest: Optional[dict] = None
        self._cache_ttl = 300  # 5 minutes

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #
    def check(self, force: bool = False) -> dict:
        """
        Check for updates and return a status dict.

        Returns:
            {
                "update_available": bool,
                "current_version": str,
                "latest_version": str,
                "manifest": dict,
                "error": str | None,
            }
        """
        if not force and self._is_cache_valid():
            return self._build_response(
                update_available=self._vm.is_newer(
                    self._cached_manifest.get("version", "")
                ),
                manifest=self._cached_manifest,
                error=None,
            )

        try:
            manifest = self._fetch_latest_manifest()
            self._cached_manifest = manifest
            self._last_check = time.time()
            return self._build_response(
                update_available=self._vm.is_newer(
                    manifest.get("version", "")
                ),
                manifest=manifest,
                error=None,
            )
        except Exception as e:
            return self._build_response(
                update_available=False,
                manifest={},
                error=str(e),
            )

    def get_download_url(self, manifest: Optional[dict] = None) -> str:
        """Return the direct-download URL for the latest release asset."""
        if manifest is None:
            manifest = self._cached_manifest
        if manifest:
            return manifest.get("download", {}).get("url", "")
        # Fallback: construct from GitHub release page
        return (
            f"https://github.com/{self.owner}/{self.repo}/releases/latest"
        )

    def get_changelog(self, manifest: Optional[dict] = None) -> str:
        """Return the changelog text for the latest release."""
        if manifest is None:
            manifest = self._cached_manifest
        return (manifest or {}).get("changelog", "")

    def get_version_file_url(self) -> str:
        """Return the raw version.json URL on the main branch."""
        return (
            f"https://raw.githubusercontent.com/{self.owner}/"
            f"{self.repo}/{self.branch}/version.json"
        )

    # ------------------------------------------------------------------ #
    #  Network                                                            #
    # ------------------------------------------------------------------ #
    def _fetch_latest_manifest(self) -> dict:
        """Fetch and parse the latest release manifest from GitHub API."""
        url = f"{self.DEFAULT_BASE_URL}/{self.owner}/{self.repo}/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "JarvisPro-Updater/1.0",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        version = tag.lstrip("v") if tag else "0.0.0"
        body = data.get("body", "")

        assets = data.get("assets", [])
        download_url = ""
        size_bytes = 0
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                size_bytes = asset.get("size", 0)
                break

        return VersionManager.build_manifest(
            version=version,
            changelog=body,
            download_url=download_url,
            size_bytes=size_bytes,
        )

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _is_cache_valid(self) -> bool:
        if self._last_check is None or self._cached_manifest is None:
            return False
        return (time.time() - self._last_check) < self._cache_ttl

    def _build_response(
        self,
        update_available: bool,
        manifest: dict,
        error: Optional[str],
    ) -> dict:
        return {
            "update_available": update_available,
            "current_version": self._vm.get_version_string(),
            "latest_version": manifest.get("version", ""),
            "manifest": manifest,
            "error": error,
        }


# ---------------------------------------------------------------------- #
#  Singleton                                                             #
# ---------------------------------------------------------------------- #
_update_checker: Optional[UpdateChecker] = None


def get_update_checker() -> UpdateChecker:
    global _update_checker
    if _update_checker is None:
        _update_checker = UpdateChecker()
    return _update_checker
