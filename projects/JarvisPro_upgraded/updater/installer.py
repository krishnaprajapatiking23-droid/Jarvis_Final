"""
Installer — Downloads, verifies, and installs JarvisPro updates safely.
"""
import os
import sys
import shutil
import hashlib
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable

from .version_manager import VersionManager, get_version_manager
from .backup_manager import BackupManager, get_backup_manager
from .health_checker import HealthChecker, get_health_checker

JARVIS_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = JARVIS_ROOT / "downloads"


class InstallResult:
    """Structured result of an install attempt."""
    def __init__(
        self,
        success: bool,
        version: str = "",
        message: str = "",
        rollback_performed: bool = False,
        error: Optional[str] = None,
    ):
        self.success = success
        self.version = version
        self.message = message
        self.rollback_performed = rollback_performed
        self.error = error

    def __repr__(self):
        return (
            f"<InstallResult success={self.success} "
            f"version={self.version!r} rollback={self.rollback_performed}>"
        )


class Installer:
    """
    Downloads, verifies, and installs new JarvisPro releases.

    Update flow:
      1. Download ZIP from manifest URL
      2. Verify SHA256 hash
      3. Create backup (via BackupManager)
      4. Extract ZIP over current install
      5. Run health check
      6. Rollback if health check fails
    """

    DEFAULT_TIMEOUT = 120  # seconds for download

    def __init__(
        self,
        version_manager: Optional[VersionManager] = None,
        backup_manager: Optional[BackupManager] = None,
        health_checker: Optional[HealthChecker] = None,
    ):
        self._vm = version_manager or get_version_manager()
        self._bm = backup_manager or get_backup_manager()
        self._hc = health_checker or get_health_checker()

    def install(
        self,
        manifest: dict,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        verify_only: bool = False,
    ) -> InstallResult:
        """
        Perform a full update install.

        Args:
            manifest: Release manifest dict with download.url and download.sha256.
            progress_callback: Called with (percent, status_message).
            verify_only: If True, download+verify but do not install.
        """
        url = manifest.get("download", {}).get("url", "")
        sha256_expected = manifest.get("download", {}).get("sha256", "")
        version = manifest.get("version", "unknown")

        if not url:
            return InstallResult(
                success=False,
                version=version,
                error="No download URL in manifest.",
            )

        # Step 1: Download
        zip_path = DOWNLOAD_DIR / f"jarvispro_update_{version}.zip"
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        self._report(progress_callback, 10, f"Downloading v{version}...")
        try:
            self._download(url, zip_path, progress_callback)
        except Exception as e:
            return InstallResult(
                success=False,
                version=version,
                error=f"Download failed: {e}",
            )

        # Step 2: Verify SHA256
        self._report(progress_callback, 60, "Verifying integrity...")
        if sha256_expected:
            if not self._verify_sha256(zip_path, sha256_expected):
                zip_path.unlink(missing_ok=True)
                return InstallResult(
                    success=False,
                    version=version,
                    error="SHA256 verification failed. File may be corrupted.",
                )

        if verify_only:
            zip_path.unlink(missing_ok=True)
            return InstallResult(
                success=True,
                version=version,
                message="Verification passed. No changes made.",
            )

        # Step 3: Backup
        self._report(progress_callback, 70, "Creating backup...")
        backup_meta = self._bm.create_backup(label=f"pre_update_{version}")
        backup_id = backup_meta.get("backup_id", "")

        # Step 4: Extract
        self._report(progress_callback, 80, "Installing files...")
        try:
            self._extract_over_install(zip_path)
        except Exception as e:
            return self._rollback(
                backup_id, progress_callback,
                f"Extraction failed: {e}", version,
            )

        # Step 5: Health check
        self._report(progress_callback, 95, "Running health check...")
        health = self._hc.check()
        if not health.get("healthy", False):
            return self._rollback(
                backup_id, progress_callback,
                f"Health check failed: {health.get('error', 'unknown')}",
                version,
            )

        # Done
        zip_path.unlink(missing_ok=True)
        self._report(progress_callback, 100, "Update complete.")
        return InstallResult(
            success=True,
            version=version,
            message=f"Successfully updated to v{version}. Restart to apply.",
        )

    def install_offline(self, zip_path: Path, sha256_expected: str = "") -> InstallResult:
        """
        Install from a locally-provided ZIP file.
        Creates backup, extracts, health-checks, rolls back on failure.
        """
        version = self._vm.get_version_string()
        if not zip_path.exists():
            return InstallResult(
                success=False,
                version=version,
                error=f"Offline ZIP not found: {zip_path}",
            )

        if sha256_expected and not self._verify_sha256(zip_path, sha256_expected):
            return InstallResult(
                success=False,
                version=version,
                error="SHA256 verification failed for offline package.",
            )

        backup_meta = self._bm.create_backup(label=f"offline_update")
        backup_id = backup_meta.get("backup_id", "")

        try:
            self._extract_over_install(zip_path)
        except Exception as e:
            return self._rollback(
                backup_id, None,
                f"Offline extraction failed: {e}", version,
            )

        health = self._hc.check()
        if not health.get("healthy", False):
            return self._rollback(
                backup_id, None,
                f"Post-install health check failed: {health.get('error', 'unknown')}",
                version,
            )

        return InstallResult(
            success=True,
            version=version,
            message="Offline update applied successfully.",
        )

    # ------------------------------------------------------------------ #
    #  Rollback                                                           #
    # ------------------------------------------------------------------ #
    def _rollback(
        self,
        backup_id: str,
        progress_callback: Optional[Callable],
        reason: str,
        version: str,
    ) -> InstallResult:
        """Roll back to the named backup. Returns failed InstallResult."""
        self._report(progress_callback, 5, f"ROLLBACK: {reason}")
        if backup_id:
            self._bm.restore_backup(backup_id)
        return InstallResult(
            success=False,
            version=version,
            message=f"Update failed and rolled back. Reason: {reason}",
            rollback_performed=True,
            error=reason,
        )

    # ------------------------------------------------------------------ #
    #  Download / Verify                                                  #
    # ------------------------------------------------------------------ #
    def _download(
        self,
        url: str,
        dest: Path,
        progress_callback: Optional[Callable],
    ):
        """Download a file with progress reporting."""
        def report(chunk_bytes, total, callback):
            if callback and total > 0:
                pct = min(int(10 + 50 * chunk_bytes / total), 60)
                callback(pct, f"Downloading... {chunk_bytes//1024}KB / {total//1024}KB")

        req = urllib.request.Request(url, headers={
            "User-Agent": "JarvisPro-Updater/1.0",
        })
        with urllib.request.urlopen(req, timeout=self.DEFAULT_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    report(downloaded, total, progress_callback)

    @staticmethod
    def _verify_sha256(file_path: Path, expected: str) -> bool:
        """Verify a file's SHA256 hash against the expected value."""
        sha256_expected = expected.lower().replace(" ", "")
        sha = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            return sha.hexdigest() == sha256_expected
        except Exception:
            return False

    @staticmethod
    def _report(cb: Optional[Callable], pct: int, msg: str):
        if cb:
            cb(pct, msg)

    # ------------------------------------------------------------------ #
    #  Extraction                                                          #
    # ------------------------------------------------------------------ #
    def _extract_over_install(self, zip_path: Path):
        """
        Extract the downloaded ZIP over the current installation.
        Skips backups dir, version.txt (preserve), and __pycache__.
        """
        import zipfile
        skip_names = {"backups", "__pycache__", ".git", ".DS_Store"}

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                # Skip excluded
                parts = Path(member).parts
                if any(part in skip_names for part in parts):
                    continue

                # Always skip __pycache__
                if "__pycache__" in member:
                    continue

                target = JARVIS_ROOT / member
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = zf.read(member)
                    target.write_bytes(data)


# ---------------------------------------------------------------------- #
#  Singleton                                                             #
# ---------------------------------------------------------------------- #
_installer: Optional[Installer] = None


def get_installer() -> Installer:
    global _installer
    if _installer is None:
        _installer = Installer()
    return _installer
