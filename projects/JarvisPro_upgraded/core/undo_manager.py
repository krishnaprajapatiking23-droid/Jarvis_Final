"""
==========================================
JARVIS PRO
Undo / rollback manager
==========================================

Roadmap sections 20 (Self-Correction: rollback) and 27 (Backup & Recovery).

This is the feature Mark-LII calls "Undo": every reversible action JARVIS
takes is journalled with enough information to put the world back. Files
that are overwritten or deleted are first copied into a local trash folder,
so undo works even for destructive operations.

Supported operations out of the box:

    file.write   - restores the previous content (or deletes a new file)
    file.create  - deletes the created file
    file.delete  - restores from the undo trash
    file.move    - moves it back
    file.rename  - renames it back
    setting      - restores the previous value through config
    custom       - any action that registers its own undo callback

Usage:

    from core.undo_manager import undo

    with undo.file_write(path):          # snapshot taken automatically
        path.write_text(new_text)

    undo.last()                          # what would be undone
    undo.undo()                          # undo the newest entry
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from config import config
from core.observability import observability


class UndoManager:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._callbacks: dict[str, Callable[[dict], bool]] = {}

        self.journal_path = Path(str(config.data_path("undo_journal.json")))
        self.trash_dir = Path(str(config.data_path("undo_trash")))

        self.trash_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------- journal io

    def _load(self) -> list[dict[str, Any]]:
        try:
            if self.journal_path.exists():
                data = json.loads(self.journal_path.read_text(encoding="utf-8"))

                if isinstance(data, list):
                    return data

        except Exception:
            pass

        return []

    def _save(self, entries: list[dict[str, Any]]) -> None:
        keep = int(config.get("undo.keep", 200))

        try:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)

            temp = self.journal_path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(entries[-keep:], indent=2, default=str),
                encoding="utf-8",
            )
            temp.replace(self.journal_path)

        except Exception as error:
            observability.warn("undo", f"journal write failed: {error}")

    # ---------------------------------------------------- recording

    def record(
        self,
        operation: str,
        description: str,
        payload: dict[str, Any],
    ) -> str:
        """Add one undoable entry and return its id."""

        entry_id = uuid.uuid4().hex[:10]

        entry = {
            "id": entry_id,
            "at": time.time(),
            "operation": operation,
            "description": description,
            "payload": payload,
            "undone": False,
        }

        with self._lock:
            entries = self._load()
            entries.append(entry)
            self._save(entries)

        observability.info("undo", f"recorded {operation}", entry=entry_id)

        return entry_id

    def _snapshot(self, path: Path) -> str:
        """Copy a file into the undo trash and return the copy's path."""

        if not path.exists() or not path.is_file():
            return ""

        target = self.trash_dir / f"{uuid.uuid4().hex[:10]}_{path.name}"

        try:
            shutil.copy2(path, target)

            return str(target)

        except Exception as error:
            observability.warn("undo", f"snapshot failed: {error}", path=str(path))

            return ""

    # ---------------------------------------------------- public helpers

    @contextmanager
    def file_write(self, path: str | Path, description: str = "") -> Iterator[str]:
        """Snapshot a file before it is written, then journal the change."""

        target = Path(path)
        existed = target.exists()
        backup = self._snapshot(target) if existed else ""

        yield str(target)

        self.record(
            "file.write" if existed else "file.create",
            description or f"wrote {target.name}",
            {"path": str(target), "backup": backup, "existed": existed},
        )

    def before_delete(self, path: str | Path, description: str = "") -> str:
        """Call right before deleting a file so undo can restore it."""

        target = Path(path)
        backup = self._snapshot(target)

        return self.record(
            "file.delete",
            description or f"deleted {target.name}",
            {"path": str(target), "backup": backup},
        )

    def after_move(
        self,
        source: str | Path,
        destination: str | Path,
        description: str = "",
    ) -> str:
        return self.record(
            "file.move",
            description or f"moved {Path(source).name}",
            {"source": str(source), "destination": str(destination)},
        )

    def setting_change(self, path: str, previous: Any, description: str = "") -> str:
        return self.record(
            "setting",
            description or f"changed {path}",
            {"setting": path, "previous": previous},
        )

    def register(self, operation: str, callback: Callable[[dict], bool]) -> None:
        """Let any manager plug its own undo logic in (custom operations)."""

        with self._lock:
            self._callbacks[operation] = callback

    # ---------------------------------------------------- undoing

    def history(self, limit: int = 20, include_undone: bool = False) -> list[dict]:
        entries = self._load()

        if not include_undone:
            entries = [item for item in entries if not item.get("undone")]

        return list(reversed(entries[-limit:]))

    def last(self) -> dict[str, Any] | None:
        items = self.history(limit=1)

        return items[0] if items else None

    def describe_last(self) -> str:
        entry = self.last()

        if not entry:
            return "There is nothing to undo."

        return f"Last undoable action: {entry['description']} ({entry['operation']})."

    def undo(self, entry_id: str = "") -> dict[str, Any]:
        """Undo one entry (the newest by default)."""

        with self._lock:
            entries = self._load()

            target = None

            for item in reversed(entries):
                if item.get("undone"):
                    continue

                if not entry_id or item["id"] == entry_id:
                    target = item
                    break

            if target is None:
                return {"ok": False, "message": "Nothing to undo."}

            ok, message = self._apply(target)

            if ok:
                target["undone"] = True
                target["undone_at"] = time.time()
                self._save(entries)

        observability.log(
            "info" if ok else "warning",
            "undo",
            message,
            entry=target["id"],
            operation=target["operation"],
        )

        return {
            "ok": ok,
            "message": message,
            "entry": target["id"],
            "operation": target["operation"],
        }

    def _apply(self, entry: dict[str, Any]) -> tuple[bool, str]:
        operation = str(entry.get("operation", ""))
        payload = dict(entry.get("payload", {}))

        try:
            if operation in ("file.write", "file.delete"):
                path = Path(str(payload.get("path", "")))
                backup = str(payload.get("backup", ""))

                if not backup or not Path(backup).exists():
                    return False, "The original content is no longer available."

                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, path)

                return True, f"Restored {path.name}."

            if operation == "file.create":
                path = Path(str(payload.get("path", "")))

                if path.exists():
                    path.unlink()

                return True, f"Removed the created file {path.name}."

            if operation in ("file.move", "file.rename"):
                source = Path(str(payload.get("source", "")))
                destination = Path(str(payload.get("destination", "")))

                if not destination.exists():
                    return False, "The moved file is no longer where it was placed."

                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))

                return True, f"Moved {source.name} back."

            if operation == "setting":
                config.set(str(payload.get("setting", "")), payload.get("previous"))

                return True, f"Restored setting {payload.get('setting')}."

            callback = self._callbacks.get(operation)

            if callback is not None:
                return bool(callback(payload)), f"Undid {operation}."

            return False, f"I do not know how to undo '{operation}'."

        except Exception as error:
            return False, f"Undo failed: {error}"

    # ---------------------------------------------------- maintenance

    def purge(self, older_than_days: float = 7.0) -> int:
        """Delete old snapshots so the trash folder cannot grow forever."""

        cutoff = time.time() - older_than_days * 86400
        removed = 0

        with self._lock:
            entries = self._load()
            keep: list[dict[str, Any]] = []

            for entry in entries:
                if entry.get("at", 0) < cutoff:
                    backup = str(entry.get("payload", {}).get("backup", ""))

                    if backup:
                        try:
                            Path(backup).unlink(missing_ok=True)

                        except Exception:
                            pass

                    removed += 1
                    continue

                keep.append(entry)

            self._save(keep)

        return removed


undo = UndoManager()
