"""
Backup Manager — creates and restores file/directory backups.

Supports:
  - Full directory snapshots
  - Incremental backup manifests
  - Restore to any previous snapshot
  - Backup metadata tracking
"""

import gzip
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional


_BACKUP_ROOT = Path(__file__).parent / "backups"
_MANIFEST_FILE = _BACKUP_ROOT / "manifest.json"


class BackupManager:

    def __init__(self, root: Path = _BACKUP_ROOT):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._manifest: Dict = self._load_manifest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def backup(self, source_path: str, label: str = None) -> Dict:
        """Create a compressed backup of source_path."""
        source = Path(source_path).resolve()
        if not source.exists():
            return {"success": False, "error": f"Source not found: {source}"}

        label = label or source.name
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"{label}_{timestamp}"
        snapshot_dir = self._root / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        file_count = 0
        total_size = 0
        checksums = {}

        try:
            for root_dir, dirs, files in os.walk(source):
                for filename in files:
                    filepath = Path(root_dir) / filename
                    rel_path = filepath.relative_to(source)
                    dest_file = snapshot_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(filepath, "rb") as src, \
                         gzip.open(dest_file.with_suffix(dest_file.suffix + ".gz"), "wb") as dst:
                        data = src.read()
                        dst.write(data)
                        checksums[str(rel_path)] = hashlib.sha256(data).hexdigest()

                    file_count += 1
                    total_size += len(data)

            manifest_entry = {
                "snapshot_id": snapshot_id,
                "label": label,
                "source": str(source),
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "file_count": file_count,
                "total_bytes": total_size,
                "checksums": checksums,
            }
            with self._lock:
                self._manifest[snapshot_id] = manifest_entry
                self._save_manifest()

            return {
                "success": True,
                "snapshot_id": snapshot_id,
                "file_count": file_count,
                "total_bytes": total_size,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restore(self, snapshot_id: str, dest_path: str) -> Dict:
        """Restore a snapshot to dest_path."""
        with self._lock:
            if snapshot_id not in self._manifest:
                return {"success": False,
                        "error": f"Snapshot '{snapshot_id}' not found"}
            entry = self._manifest[snapshot_id]

        snapshot_dir = self._root / snapshot_id
        dest = Path(dest_path)

        try:
            for root_dir, dirs, files in os.walk(snapshot_dir):
                for filename in files:
                    src_file = Path(root_dir) / filename
                    rel_path = src_file.relative_to(snapshot_dir)
                    # Strip .gz suffix to get original filename
                    original_name = rel_path.with_suffix(
                        rel_path.stem if rel_path.suffix == ".gz"
                        else rel_path.name)
                    dest_file = dest / original_name
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    with gzip.open(src_file, "rb") as src, \
                         open(dest_file, "wb") as dst:
                        dst.write(src.read())

            return {
                "success": True,
                "restored_to": str(dest),
                "files": entry["file_count"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_snapshots(self) -> List[Dict]:
        """Return all backup snapshots."""
        return list(self._manifest.values())

    def delete_snapshot(self, snapshot_id: str) -> Dict:
        """Delete a snapshot and its files."""
        with self._lock:
            if snapshot_id not in self._manifest:
                return {"success": False,
                        "error": f"Snapshot '{snapshot_id}' not found"}
            snapshot_dir = self._root / snapshot_id
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir)
            del self._manifest[snapshot_id]
            self._save_manifest()
            return {"success": True, "deleted": snapshot_id}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_manifest(self) -> Dict:
        try:
            if _MANIFEST_FILE.exists():
                with open(_MANIFEST_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_manifest(self):
        try:
            with open(_MANIFEST_FILE, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


_manager = BackupManager()

backup = _manager.backup
restore = _manager.restore
list_snapshots = _manager.list_snapshots
delete_snapshot = _manager.delete_snapshot
