"""
Backup Manager — Creates and manages point-in-time backups of JarvisPro.
"""
import os
import shutil
import time
import json
from pathlib import Path
from typing import List, Optional, Tuple

JARVIS_ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = JARVIS_ROOT / "backups"
METADATA_FILE = "backup_meta.json"
MAX_BACKUPS = 10


class BackupManager:
    """
    Manages rolling backups of the JarvisPro installation.
    Each backup is a timestamped snapshot of the project directory.
    """

    def __init__(self, backup_root: Optional[Path] = None):
        self.backup_root = (backup_root or BACKUP_ROOT).resolve()
        self._ensure_backup_dir()

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #
    def create_backup(self, label: str = "") -> dict:
        """
        Create a full snapshot of the JarvisPro directory.

        Returns:
            {
                "backup_id": str,
                "path": str,
                "size_bytes": int,
                "file_count": int,
                "created_at": str,
                "label": str,
            }
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}"
        backup_path = self.backup_root / backup_id

        # Copy everything except __pycache__, .git, *.pyc, etc.
        excluded = {
            "__pycache__", ".git", ".pytest_cache",
            "node_modules", ".venv", "venv",
            "*.pyc", "*.pyo", ".DS_Store",
            "backups", "dist", "build", "*.egg-info",
        }
        copied_count = self._copy_tree(JARVIS_ROOT, backup_path, excluded)
        total_size = self._dir_size(backup_path)

        meta = {
            "backup_id": backup_id,
            "path": str(backup_path),
            "size_bytes": total_size,
            "file_count": copied_count,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "label": label or "",
            "version": self._read_version(),
        }

        self._save_meta(backup_id, meta)
        self._prune_old_backups()
        return meta

    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore JarvisPro from a named backup.
        Creates a pre-restore snapshot automatically.
        """
        backup_path = self.backup_root / backup_id
        if not backup_path.exists():
            return False

        # Pre-restore safety snapshot
        self.create_backup(label="pre_restore_safety")

        # Remove current files (except backups dir)
        for item in JARVIS_ROOT.iterdir():
            if item.name in ("backups",):
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                pass

        # Restore from backup
        for item in backup_path.iterdir():
            dest = JARVIS_ROOT / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            except Exception:
                pass

        return True

    def list_backups(self) -> List[dict]:
        """Return metadata for all existing backups, newest first."""
        self._ensure_backup_dir()
        backups = []
        for sub in self.backup_root.iterdir():
            if sub.is_dir() and sub.name.startswith("backup_"):
                meta = self._load_meta(sub.name)
                if meta:
                    backups.append(meta)
        backups.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return backups

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a specific backup permanently."""
        backup_path = self.backup_root / backup_id
        if backup_path.exists():
            shutil.rmtree(backup_path)
            self._delete_meta(backup_id)
            return True
        return False

    def get_latest_backup(self) -> Optional[dict]:
        """Return metadata for the most recent backup."""
        all_backups = self.list_backups()
        return all_backups[0] if all_backups else None

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _ensure_backup_dir(self):
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def _read_version(self) -> str:
        vf = JARVIS_ROOT / "version.txt"
        if vf.exists():
            return vf.read_text(encoding="utf-8").strip()
        return "unknown"

    def _save_meta(self, backup_id: str, meta: dict):
        meta_path = self.backup_root / f"{backup_id}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _load_meta(self, backup_id: str) -> Optional[dict]:
        meta_path = self.backup_root / f"{backup_id}.meta.json"
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _delete_meta(self, backup_id: str):
        meta_path = self.backup_root / f"{backup_id}.meta.json"
        if meta_path.exists():
            meta_path.unlink()

    def _prune_old_backups(self):
        """Remove oldest backups until under MAX_BACKUPS."""
        backups = self.list_backups()
        if len(backups) <= MAX_BACKUPS:
            return
        for old in backups[MAX_BACKUPS:]:
            self.delete_backup(old["backup_id"])

    @staticmethod
    def _copy_tree(src: Path, dst: Path, excluded: set) -> int:
        """Copy src tree to dst, excluding patterns. Returns file count."""
        dst.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in src.iterdir():
            if any(
                item.name == ex or item.match(ex)
                for ex in excluded
            ):
                continue
            dest = dst / item.name
            if item.is_dir():
                count += BackupManager._copy_tree(item, dest, excluded)
            else:
                try:
                    shutil.copy2(item, dest)
                    count += 1
                except Exception:
                    pass
        return count

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except Exception:
                    pass
        return total


# ---------------------------------------------------------------------- #
#  Singleton                                                             #
# ---------------------------------------------------------------------- #
_backup_manager: Optional[BackupManager] = None


def get_backup_manager() -> BackupManager:
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager
