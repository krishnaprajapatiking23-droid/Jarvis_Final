"""
Research Manager — systematic research, source gathering, and synthesis.

Capabilities:
  - Topic research with source tracking
  - Comparison reports
  - Web search integration (via browser/requests)
  - Structured notes extraction
  - Research session management
"""

import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional


_DATA_DIR = Path(__file__).parent / "data"
_CURRENT_SESSION_FILE = _DATA_DIR / "current_research.json"


class ResearchSession:
    """Tracks a single research session."""

    def __init__(self, topic: str):
        self.topic = topic
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.notes: List[Dict] = []
        self.sources: List[str] = []
        self.sections: List[Dict] = []
        self.status = "active"

    def add_note(self, heading: str, content: str) -> None:
        self.notes.append({
            "heading": heading,
            "content": content[:500],
            "ts": time.strftime("%H:%M:%S"),
        })

    def add_source(self, url: str, title: str = "") -> None:
        self.sources.append({"url": url, "title": title,
                             "added": time.strftime("%H:%M:%S")})

    def add_section(self, title: str, summary: str) -> None:
        self.sections.append({"title": title, "summary": summary})

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "started_at": self.started_at,
            "status": self.status,
            "notes": self.notes,
            "sources": self.sources,
            "sections": self.sections,
        }


class ResearchManager:

    def __init__(self):
        self._sessions: Dict[str, ResearchSession] = {}
        self._active: Optional[str] = None
        self._lock = Lock()
        self._load_active()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start(self, topic: str) -> Dict:
        """Start a new research session on a topic."""
        session_id = f"research_{int(time.time())}"
        session = ResearchSession(topic)
        with self._lock:
            self._sessions[session_id] = session
            self._active = session_id
            self._save_active(session)
        return {
            "success": True,
            "session_id": session_id,
            "topic": topic,
        }

    def end(self) -> Dict:
        """Mark the current session as complete."""
        with self._lock:
            if self._active and self._active in self._sessions:
                self._sessions[self._active].status = "complete"
                result = self._sessions[self._active].to_dict()
                self._active = None
                self._save_active(None)
                return {"success": True, **result}
        return {"success": False, "error": "No active session"}

    def current(self) -> Optional[ResearchSession]:
        if self._active:
            return self._sessions.get(self._active)
        return None

    # ------------------------------------------------------------------
    # Research operations
    # ------------------------------------------------------------------

    def note(self, heading: str, content: str) -> Dict:
        """Add a note to the active session."""
        session = self.current()
        if not session:
            return {"success": False, "error": "No active research session"}
        session.add_note(heading, content)
        self._save_active(session)
        return {"success": True, "note_count": len(session.notes)}

    def cite(self, url: str, title: str = "") -> Dict:
        """Add a source URL to the active session."""
        session = self.current()
        if not session:
            return {"success": False, "error": "No active research session"}
        session.add_source(url, title)
        self._save_active(session)
        return {"success": True, "source_count": len(session.sources)}

    def section(self, title: str, summary: str) -> Dict:
        """Add a section heading and summary to the active session."""
        session = self.current()
        if not session:
            return {"success": False, "error": "No active research session"}
        session.add_section(title, summary)
        self._save_active(session)
        return {"success": True, "section_count": len(session.sections)}

    def compile(self) -> Dict:
        """Compile the active research session into a full report."""
        session = self.current()
        if not session:
            return {"success": False, "error": "No active research session"}

        report_lines = [
            f"# Research: {session.topic}",
            f"Started: {session.started_at}",
            "",
            "## Sources",
        ]
        for src in session.sources:
            report_lines.append(f"- [{src['title']}]({src['url']})")

        report_lines.extend(["", "## Notes", ""])
        for note in session.notes:
            report_lines.append(f"### {note['heading']} ({note['ts']})")
            report_lines.append(note["content"])
            report_lines.append("")

        report_lines.extend(["", "## Summary", ""])
        for sec in session.sections:
            report_lines.append(f"### {sec['title']}")
            report_lines.append(sec["summary"])
            report_lines.append("")

        return {
            "success": True,
            "topic": session.topic,
            "sources": len(session.sources),
            "notes": len(session.notes),
            "report": "\n".join(report_lines),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_active(self, session: Optional[ResearchSession]) -> None:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            if session is None:
                if _CURRENT_SESSION_FILE.exists():
                    _CURRENT_SESSION_FILE.unlink()
                return
            import json
            with open(_CURRENT_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_active(self) -> None:
        try:
            if _CURRENT_SESSION_FILE.exists():
                import json
                with open(_CURRENT_SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    topic = data.get("topic", "Unknown")
                    session = ResearchSession(topic)
                    session.notes = data.get("notes", [])
                    session.sources = data.get("sources", [])
                    session.sections = data.get("sections", [])
                    session.status = data.get("status", "active")
                    self._sessions["active"] = session
                    if session.status == "active":
                        self._active = "active"
        except Exception:
            pass


_manager = ResearchManager()

start = _manager.start
end = _manager.end
note = _manager.note
cite = _manager.cite
section = _manager.section
compile = _manager.compile
current = _manager.current
