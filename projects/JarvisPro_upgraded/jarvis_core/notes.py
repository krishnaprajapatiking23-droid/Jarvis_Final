"""Section 7 - notes manager with real version history.

Every create/edit/restore/delete writes an immutable row into
``note_versions``, so history survives edits and deletions. Deletion is a
soft delete (``status='deleted'``) precisely so version history is never
destroyed; ``purge()`` is the explicit, separate hard delete.

``compare(note_id, a, b)`` returns a real unified diff between two versions.

Storage: ``data/notes.db``.
"""
from __future__ import annotations

import difflib
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

STATUS_ACTIVE, STATUS_DELETED = "active", "deleted"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


@dataclass
class Note:
    note_id: str
    title: str
    body: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    important: bool = False
    version: int = 1
    status: str = STATUS_ACTIVE
    created_at: str = field(default_factory=_utc)
    updated_at: str = field(default_factory=_utc)

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        data["tags"] = list(self.tags)
        return data


class NotesManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "notes.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    note_id TEXT PRIMARY KEY, title TEXT, body TEXT, category TEXT, tags TEXT,
                    important INTEGER, version INTEGER, status TEXT, created_at TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS note_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id TEXT, version INTEGER, title TEXT, body TEXT, category TEXT, tags TEXT,
                    important INTEGER, status TEXT, action TEXT, actor TEXT, created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_note_versions ON note_versions(note_id, version);
                """
            )
            self._conn.commit()

    # ---------------- helpers ----------------
    def _row(self, note_id: str) -> Note:
        row = self._conn.execute("SELECT * FROM notes WHERE note_id=?", (note_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown note {note_id}")
        data = dict(row)
        data["tags"] = [t for t in (data.pop("tags") or "").split(",") if t]
        data["important"] = bool(data["important"])
        return Note(**data)

    def _record_version(self, note: Note, action: str, actor: str) -> None:
        self._conn.execute(
            "INSERT INTO note_versions(note_id, version, title, body, category, tags, important,"
            " status, action, actor, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (note.note_id, note.version, note.title, note.body, note.category,
             ",".join(note.tags), int(note.important), note.status, action, actor, _utc()),
        )

    def auto_tags(self, title: str, body: str) -> List[str]:
        text = f"{title} {body}".lower()
        rules = {
            "idea": r"\bidea|concept|brainstorm\b",
            "todo": r"\btodo|task|must|need to\b",
            "code": r"\bpython|function|bug|api|class\b",
            "study": r"\bstudy|exam|revision|chapter\b",
            "money": r"\bbudget|price|cost|invoice|rupees|\$\b",
            "motivation": r"\bdiscipline|success|goal|focus\b",
        }
        return sorted(tag for tag, pattern in rules.items() if re.search(pattern, text))

    # ---------------- CRUD ----------------
    def create(self, title: str, body: str = "", *, category: str = "general",
               tags: Optional[Sequence[str]] = None, important: bool = False,
               actor: str = "owner") -> Note:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("note title must be a non-empty string")
        note = Note(
            note_id="N-" + uuid.uuid4().hex[:10], title=title.strip(), body=body,
            category=category, important=bool(important),
            tags=list(tags) if tags is not None else self.auto_tags(title, body),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO notes(note_id, title, body, category, tags, important, version,"
                " status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (note.note_id, note.title, note.body, note.category, ",".join(note.tags),
                 int(note.important), 1, note.status, note.created_at, note.updated_at),
            )
            self._record_version(note, "created", actor)
            self._conn.commit()
        return note

    def get(self, note_id: str) -> Note:
        with self._lock:
            return self._row(note_id)

    def list(self, *, category: Optional[str] = None, include_deleted: bool = False,
             limit: int = 50) -> List[Note]:
        query = "SELECT note_id FROM notes WHERE 1=1"
        params: List[Any] = []
        if not include_deleted:
            query += " AND status=?"
            params.append(STATUS_ACTIVE)
        if category:
            query += " AND category=?"
            params.append(category)
        query += " ORDER BY important DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            ids = [row["note_id"] for row in self._conn.execute(query, params).fetchall()]
            return [self._row(note_id) for note_id in ids]

    def search(self, term: str, limit: int = 20) -> List[Note]:
        like = f"%{term.lower()}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT note_id FROM notes WHERE status=? AND (lower(title) LIKE ?"
                " OR lower(body) LIKE ? OR lower(tags) LIKE ?) ORDER BY updated_at DESC LIMIT ?",
                (STATUS_ACTIVE, like, like, like, limit),
            ).fetchall()
            return [self._row(row["note_id"]) for row in rows]

    def edit(self, note_id: str, *, title: Optional[str] = None, body: Optional[str] = None,
             category: Optional[str] = None, tags: Optional[Sequence[str]] = None,
             important: Optional[bool] = None, actor: str = "owner") -> Note:
        with self._lock:
            note = self._row(note_id)
            if note.status == STATUS_DELETED:
                raise ValueError(f"note {note_id} is deleted; restore it before editing")
            if title is not None:
                if not title.strip():
                    raise ValueError("title may not be blank")
                note.title = title.strip()
            if body is not None:
                note.body = body
            if category is not None:
                note.category = category
            if tags is not None:
                note.tags = list(tags)
            if important is not None:
                note.important = bool(important)
            note.version += 1
            note.updated_at = _utc()
            self._conn.execute(
                "UPDATE notes SET title=?, body=?, category=?, tags=?, important=?, version=?,"
                " updated_at=? WHERE note_id=?",
                (note.title, note.body, note.category, ",".join(note.tags), int(note.important),
                 note.version, note.updated_at, note_id),
            )
            self._record_version(note, "edited", actor)
            self._conn.commit()
            return note

    def delete(self, note_id: str, actor: str = "owner") -> Note:
        """Soft delete - version history is preserved."""
        with self._lock:
            note = self._row(note_id)
            note.status = STATUS_DELETED
            note.version += 1
            note.updated_at = _utc()
            self._conn.execute("UPDATE notes SET status=?, version=?, updated_at=? WHERE note_id=?",
                               (note.status, note.version, note.updated_at, note_id))
            self._record_version(note, "deleted", actor)
            self._conn.commit()
            return note

    def undelete(self, note_id: str, actor: str = "owner") -> Note:
        with self._lock:
            note = self._row(note_id)
            note.status = STATUS_ACTIVE
            note.version += 1
            note.updated_at = _utc()
            self._conn.execute("UPDATE notes SET status=?, version=?, updated_at=? WHERE note_id=?",
                               (note.status, note.version, note.updated_at, note_id))
            self._record_version(note, "undeleted", actor)
            self._conn.commit()
            return note

    def purge(self, note_id: str, actor: str = "owner") -> Dict[str, Any]:
        """Explicit hard delete, including history. Requires the note be deleted first."""
        with self._lock:
            note = self._row(note_id)
            if note.status != STATUS_DELETED:
                raise ValueError("purge requires the note to be deleted first")
            versions = self._conn.execute(
                "SELECT COUNT(*) c FROM note_versions WHERE note_id=?", (note_id,)).fetchone()["c"]
            self._conn.execute("DELETE FROM note_versions WHERE note_id=?", (note_id,))
            self._conn.execute("DELETE FROM notes WHERE note_id=?", (note_id,))
            self._conn.commit()
        return {"purged": note_id, "versions_removed": versions, "actor": actor}

    # ---------------- version history ----------------
    def versions(self, note_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM note_versions WHERE note_id=? ORDER BY version, id",
                (note_id,)).fetchall()
        if not rows:
            raise KeyError(f"no version history for {note_id}")
        out = []
        for row in rows:
            item = dict(row)
            item["tags"] = [t for t in (item["tags"] or "").split(",") if t]
            item["important"] = bool(item["important"])
            out.append(item)
        return out

    def version(self, note_id: str, version: int) -> Dict[str, Any]:
        for item in self.versions(note_id):
            if item["version"] == version:
                return item
        raise KeyError(f"note {note_id} has no version {version}")

    def compare(self, note_id: str, left: int, right: int) -> Dict[str, Any]:
        a, b = self.version(note_id, left), self.version(note_id, right)
        diff = list(difflib.unified_diff(
            a["body"].splitlines(), b["body"].splitlines(),
            fromfile=f"v{left}", tofile=f"v{right}", lineterm=""))
        changed = [key for key in ("title", "body", "category", "important")
                   if a[key] != b[key]]
        return {"note_id": note_id, "from": left, "to": right, "changed_fields": changed,
                "diff": "\n".join(diff), "identical": not changed}

    def restore(self, note_id: str, version: int, actor: str = "owner") -> Note:
        """Restore an old version as a *new* version (history is append-only)."""
        snapshot = self.version(note_id, version)
        with self._lock:
            note = self._row(note_id)
            note.title = snapshot["title"]
            note.body = snapshot["body"]
            note.category = snapshot["category"]
            note.tags = list(snapshot["tags"])
            note.important = snapshot["important"]
            note.status = STATUS_ACTIVE
            note.version += 1
            note.updated_at = _utc()
            self._conn.execute(
                "UPDATE notes SET title=?, body=?, category=?, tags=?, important=?, status=?,"
                " version=?, updated_at=? WHERE note_id=?",
                (note.title, note.body, note.category, ",".join(note.tags), int(note.important),
                 note.status, note.version, note.updated_at, note_id),
            )
            self._record_version(note, f"restored from v{version}", actor)
            self._conn.commit()
            return note

    def summarize(self, note_id: str, max_sentences: int = 2) -> str:
        note = self.get(note_id)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", note.body) if s.strip()]
        if not sentences:
            return note.title
        return " ".join(sentences[:max_sentences])

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            active = self._conn.execute("SELECT COUNT(*) c FROM notes WHERE status=?",
                                        (STATUS_ACTIVE,)).fetchone()["c"]
            deleted = self._conn.execute("SELECT COUNT(*) c FROM notes WHERE status=?",
                                         (STATUS_DELETED,)).fetchone()["c"]
            versions = self._conn.execute("SELECT COUNT(*) c FROM note_versions").fetchone()["c"]
        return {"active": active, "deleted": deleted, "versions": versions}


_NOTES: Optional[NotesManager] = None
_NOTES_LOCK = threading.RLock()


def get_notes_manager(**kwargs: Any) -> NotesManager:
    global _NOTES
    with _NOTES_LOCK:
        if _NOTES is None:
            _NOTES = NotesManager(**kwargs)
        return _NOTES
