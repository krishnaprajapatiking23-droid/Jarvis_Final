"""
==========================================
JARVIS PRO
Backup & recovery manager
==========================================

Roadmap section 27.

Creates versioned snapshots of the things that are painful to lose - the
configuration, the databases and the JSON memory stores - and can restore
any snapshot again. Used by the self-improvement layer as its safety net:
backup -> change -> test -> keep or rollback.

Snapshots are plain zip files under ``data/backups`` so they can be copied
out or opened by hand.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from config import config
from core.observability import observability


# Directories/files worth protecting, relative to the project root.
DEFAULT_TARGETS = [
    "config",
    "data",
]

SKIP_NAMES = {
    "backups",
    "undo_trash",
    "__pycache__",
    "observability.db",
}

SKIP_SUFFIXES = {".pyc", ".tmp", ".log", ".zip"}

# Never put credentials inside a snapshot.
SECRET_NAMES = {"api_keys.json", ".env"}


class BackupManager:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.root = Path(str(config.path()))
        self.backup_dir = Path(str(config.data_path("backups")))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------- helpers

    def _collect(self, targets: list[str]) -> list[Path]:
        files: list[Path] = []

        for target in targets:
            base = self.root / target

            if not base.exists():
                continue

            if base.is_file():
                files.append(base)
                continue

            for path in base.rglob("*"):
                if not path.is_file():
                    continue

                if any(part in SKIP_NAMES for part in path.parts):
                    continue

                if path.suffix.lower() in SKIP_SUFFIXES:
                    continue

                if path.name in SECRET_NAMES:
                    continue

                files.append(path)

        return files

    # ---------------------------------------------------- creating

    def create(
        self,
        label: str = "manual",
        targets: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a snapshot and return its metadata."""

        targets = targets or list(DEFAULT_TARGETS)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in label
        )[:40]

        archive = self.backup_dir / f"{stamp}_{safe_label}.zip"

        with self._lock:
            files = self._collect(targets)

            if not files:
                return {"ok": False, "message": "Nothing to back up."}

            try:
                with zipfile.ZipFile(
                    archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                ) as bundle:
                    for path in files:
                        bundle.write(path, path.relative_to(self.root).as_posix())

                    bundle.writestr(
                        "_backup.json",
                        json.dumps(
                            {
                                "label": label,
                                "created_at": time.time(),
                                "created_readable": stamp,
                                "targets": targets,
                                "file_count": len(files),
                            },
                            indent=2,
                        ),
                    )

            except Exception as error:
                observability.error("backup", f"snapshot failed: {error}")

                return {"ok": False, "message": f"Backup failed: {error}"}

            self.prune()

        observability.info("backup", "snapshot created", archive=archive.name)

        return {
            "ok": True,
            "name": archive.name,
            "path": str(archive),
            "files": len(files),
            "size": archive.stat().st_size,
            "label": label,
        }

    # ---------------------------------------------------- listing

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for archive in sorted(self.backup_dir.glob("*.zip"), reverse=True):
            try:
                info = archive.stat()

                items.append(
                    {
                        "name": archive.name,
                        "path": str(archive),
                        "size": info.st_size,
                        "created_at": info.st_mtime,
                        "created_readable": datetime.fromtimestamp(
                            info.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            except Exception:
                continue

        return items

    def latest(self) -> dict[str, Any] | None:
        items = self.list()

        return items[0] if items else None

    # ---------------------------------------------------- restoring

    def restore(self, name: str = "", dry_run: bool = False) -> dict[str, Any]:
        """Restore a snapshot (the newest one when no name is given).

        The current state is snapshotted first, so a restore is itself
        reversible.
        """

        with self._lock:
            if name:
                archive = self.backup_dir / name
            else:
                newest = self.latest()
                archive = Path(newest["path"]) if newest else Path()

            if not archive.exists():
                return {"ok": False, "message": "That backup does not exist."}

            try:
                with zipfile.ZipFile(archive) as bundle:
                    members = [
                        item
                        for item in bundle.namelist()
                        if item != "_backup.json"
                        and not item.startswith("/")
                        and ".." not in item
                    ]

                    if dry_run:
                        return {
                            "ok": True,
                            "message": f"{len(members)} files would be restored.",
                            "files": members[:50],
                        }

                    self.create(label="pre_restore")

                    for item in members:
                        destination = self.root / item
                        destination.parent.mkdir(parents=True, exist_ok=True)

                        with bundle.open(item) as source, open(
                            destination, "wb"
                        ) as output:
                            shutil.copyfileobj(source, output)

            except Exception as error:
                observability.error("backup", f"restore failed: {error}")

                return {"ok": False, "message": f"Restore failed: {error}"}

        config.reload()

        observability.info("backup", "snapshot restored", archive=archive.name)

        return {
            "ok": True,
            "message": f"Restored {len(members)} files from {archive.name}.",
            "name": archive.name,
            "files": len(members),
        }

    def rollback(self) -> dict[str, Any]:
        """Alias used by the self-improvement loop."""

        return self.restore()

    # ---------------------------------------------------- maintenance

    def prune(self) -> int:
        keep = max(int(config.get("backup.keep", 10)), 1)
        archives = sorted(self.backup_dir.glob("*.zip"), reverse=True)
        removed = 0

        for archive in archives[keep:]:
            try:
                archive.unlink()
                removed += 1

            except Exception:
                continue

        return removed

    def status(self) -> dict[str, Any]:
        items = self.list()

        return {
            "folder": str(self.backup_dir),
            "count": len(items),
            "keep": int(config.get("backup.keep", 10)),
            "latest": items[0] if items else None,
            "total_size": sum(item["size"] for item in items),
        }


backup = BackupManager()
