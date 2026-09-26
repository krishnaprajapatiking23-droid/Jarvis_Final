"""
==========================================
JARVIS PRO
Mistake learning
==========================================

Roadmap sections 20 (self-correction) and 23: remember mistakes so the same
one is not repeated, and remember the fix that worked.

This file was an empty stub. It now keeps a small JSON journal of failures
and their resolutions, keyed by the error signature.

    from learning.mistakes import mistakes

    mistakes.record("open notepad", "FileNotFoundError: notepad")
    mistakes.resolve("FileNotFoundError: notepad", "use the full exe path")
    mistakes.known_fix("FileNotFoundError: notepad")
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any


KEEP = 300


class MistakeJournal:
    """Remembers what went wrong and what fixed it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ---------------------------------------------------- storage

    def _path(self) -> Path:
        try:
            from config import config

            return config.data_path() / "mistakes.json"

        except Exception:
            return Path("data/mistakes.json")

    def _load(self) -> list[dict[str, Any]]:
        path = self._path()

        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            return data if isinstance(data, list) else []

        except Exception:
            return []

    def _save(self, records: list[dict[str, Any]]) -> None:
        path = self._path()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(records[-KEEP:], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        except Exception:
            pass

    # ---------------------------------------------------- helpers

    def signature(self, error: str) -> str:
        """Stable fingerprint: error type plus its stable words."""

        text = str(error or "").strip()

        if not text:
            return ""

        # drop paths, numbers and quoted values so similar errors group
        cleaned = re.sub(r"[\"'][^\"']*[\"']", "", text)
        cleaned = re.sub(r"[A-Za-z]:\\\\[^\s]*|/[^\s]*/", "", cleaned)
        cleaned = re.sub(r"\d+", "", cleaned)
        words = re.findall(r"[A-Za-z]+", cleaned)

        return " ".join(words[:8]).lower()

    # ---------------------------------------------------- writing

    def record(self, goal: str, error: str, context: str = "") -> dict[str, Any]:
        """Log a mistake, or increase the count if it is a repeat."""

        fingerprint = self.signature(error)

        if not fingerprint:
            return {"ok": False, "error": "nothing to record"}

        with self._lock:
            records = self._load()

            for item in records:
                if item.get("signature") == fingerprint:
                    item["times"] = int(item.get("times", 1)) + 1
                    item["last_seen"] = time.time()
                    item["last_goal"] = str(goal or "")[:200]
                    self._save(records)

                    return {"ok": True, "repeat": True, **item}

            entry = {
                "signature": fingerprint,
                "error": str(error or "")[:400],
                "goal": str(goal or "")[:200],
                "last_goal": str(goal or "")[:200],
                "context": str(context or "")[:300],
                "times": 1,
                "first_seen": time.time(),
                "last_seen": time.time(),
                "fix": "",
                "resolved": False,
            }
            records.append(entry)
            self._save(records)

            return {"ok": True, "repeat": False, **entry}

    def resolve(self, error: str, fix: str) -> bool:
        """Attach the fix that actually worked."""

        fingerprint = self.signature(error)

        if not fingerprint or not str(fix or "").strip():
            return False

        with self._lock:
            records = self._load()

            for item in records:
                if item.get("signature") == fingerprint:
                    item["fix"] = str(fix)[:300]
                    item["resolved"] = True
                    item["resolved_at"] = time.time()
                    self._save(records)

                    return True

        return False

    # ---------------------------------------------------- reading

    def known_fix(self, error: str) -> str:
        """The fix for this error, if JARVIS has solved it before."""

        fingerprint = self.signature(error)

        if not fingerprint:
            return ""

        for item in self._load():
            if item.get("signature") == fingerprint and item.get("resolved"):
                return str(item.get("fix") or "")

        return ""

    def seen_before(self, error: str) -> bool:
        fingerprint = self.signature(error)

        return any(
            item.get("signature") == fingerprint for item in self._load()
        )

    def repeated(self, minimum: int = 2) -> list[dict[str, Any]]:
        """Mistakes that keep happening and still have no fix."""

        records = [
            item
            for item in self._load()
            if int(item.get("times", 1)) >= minimum and not item.get("resolved")
        ]
        records.sort(key=lambda item: int(item.get("times", 1)), reverse=True)

        return records

    def all_mistakes(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._load()[-limit:]

    def advice(self, error: str) -> str:
        """One sentence to add to a retry or re-plan prompt."""

        fix = self.known_fix(error)

        if fix:
            return f"You solved this before by: {fix}"

        if self.seen_before(error):
            return "This error has happened before and was never solved; try something different."

        return ""

    def clear(self) -> int:
        with self._lock:
            count = len(self._load())
            self._save([])

            return count

    def status(self) -> dict[str, Any]:
        records = self._load()

        return {
            "total": len(records),
            "resolved": sum(1 for item in records if item.get("resolved")),
            "unresolved_repeats": len(self.repeated()),
        }


mistakes = MistakeJournal()
