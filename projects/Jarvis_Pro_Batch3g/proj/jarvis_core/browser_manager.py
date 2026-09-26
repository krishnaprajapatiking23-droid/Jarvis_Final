"""Browser manager (Section 13).

Selector-first browser automation: form filling, download management, upload
handling, sessions, active-tab tracking, CAPTCHA detection and per-action
verification. Screen coordinates are never used.

The manager talks to a *driver port* (`BrowserDriver` protocol) so the same
logic runs on Playwright, Selenium, or the in-process `NullDriver` used when no
browser is installed. Without a driver every call returns a clean
`unavailable` outcome instead of pretending to have acted.

CAPTCHA policy: detection stops the operation and asks for a human. Jarvis
never attempts to solve or bypass a CAPTCHA.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CAPTCHA_MARKERS = (
    "recaptcha", "g-recaptcha", "hcaptcha", "h-captcha", "cf-turnstile",
    "funcaptcha", "arkoselabs", "are you a robot", "i'm not a robot",
    "verify you are human", "captcha",
)

SENSITIVE_FIELD = re.compile(r"pass|secret|token|cvv|card|ssn|otp", re.I)

STATUS_OK = "ok"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _outcome(status: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": status == STATUS_OK, "status": status}
    out.update(extra)
    return out


class CaptchaRequiresHuman(RuntimeError):
    """Raised/reported when a CAPTCHA blocks an automated flow."""


class BrowserDriver:
    """Port implemented by real drivers (Playwright/Selenium) and test doubles.

    Required methods: open(url), current_url(), page_source(), find(selector),
    fill(selector, value), click(selector), text_of(selector),
    upload(selector, path), downloads(), tabs(), switch(index), close().
    """

    name = "abstract"


class NullDriver(BrowserDriver):
    """Used when no browser backend exists. Refuses every action honestly."""

    name = "null"

    def __getattr__(self, item):
        def _unavailable(*_a, **_k):
            raise RuntimeError("no browser backend installed (playwright/selenium missing)")
        return _unavailable


@dataclass
class BrowserSession:
    id: str
    profile: str = "default"
    created_at: str = field(default_factory=_utc)
    last_used: str = field(default_factory=_utc)
    tabs: List[str] = field(default_factory=list)
    active_tab: int = 0
    closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "profile": self.profile, "created_at": self.created_at,
                "last_used": self.last_used, "tabs": list(self.tabs),
                "active_tab": self.active_tab, "closed": self.closed}


class BrowserManager:
    """Capability: "browser". Registered on the kernel manager registry.

    State: sessions in memory, action/verification history and downloads in
    SQLite (`browser.db`) so history survives restart.
    """

    capability = "browser"

    def __init__(self, db_path: Optional[str] = None, driver: Optional[BrowserDriver] = None,
                 kernel: Any = None, download_dir: Optional[str] = None):
        self.kernel = kernel
        self.driver = driver or NullDriver()
        self.download_dir = download_dir or os.path.join(_DEF_DIR, "downloads")
        path = db_path or os.path.join(_DEF_DIR, "browser.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._sessions: Dict[str, BrowserSession] = {}
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS browser_actions(
                    id TEXT PRIMARY KEY, session TEXT, action TEXT, target TEXT,
                    expected TEXT, actual TEXT, verified INTEGER, status TEXT,
                    detail TEXT, at TEXT);
                CREATE TABLE IF NOT EXISTS browser_downloads(
                    id TEXT PRIMARY KEY, session TEXT, url TEXT, path TEXT,
                    bytes INTEGER, state TEXT, detail TEXT, at TEXT);
                CREATE INDEX IF NOT EXISTS idx_actions_session ON browser_actions(session);
                """
            )
            self._conn.commit()

    # ---------------- infrastructure ----------------
    def _guard(self, scope: str, action: str) -> Dict[str, Any]:
        if self.kernel is None or not hasattr(self.kernel, "guard"):
            return {"allowed": True, "reason": "no policy engine attached"}
        try:
            return self.kernel.guard(scope, action)
        except Exception as exc:
            return {"allowed": False, "reason": f"policy error: {type(exc).__name__}: {exc}"}

    def _log(self, session: str, action: str, target: str, expected: Any, actual: Any,
             verified: bool, status: str, detail: str = "") -> Dict[str, Any]:
        record = {
            "id": "BA-" + uuid.uuid4().hex[:10], "session": session, "action": action,
            "target": target, "expected": json.dumps(expected, default=str),
            "actual": json.dumps(actual, default=str), "verified": int(bool(verified)),
            "status": status, "detail": detail, "at": _utc(),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO browser_actions(id, session, action, target, expected, actual,"
                " verified, status, detail, at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                tuple(record[k] for k in ("id", "session", "action", "target", "expected",
                                          "actual", "verified", "status", "detail", "at")))
            self._conn.commit()
        analytics = getattr(self.kernel, "analytics", None)
        if analytics is not None:
            try:
                analytics.record("tool", f"browser.{action}", status == STATUS_OK,
                                 error=detail or None)
            except Exception:
                pass
        return record

    def history(self, session: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM browser_actions"
        params: List[Any] = []
        if session:
            sql += " WHERE session=?"
            params.append(session)
        sql += " ORDER BY at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def health(self) -> Dict[str, Any]:
        return {"available": not isinstance(self.driver, NullDriver),
                "driver": getattr(self.driver, "name", type(self.driver).__name__),
                "sessions": len([s for s in self._sessions.values() if not s.closed]),
                "download_dir": self.download_dir}

    # ---------------- sessions / tabs ----------------
    def open_session(self, profile: str = "default") -> Dict[str, Any]:
        session = BrowserSession(id="BS-" + uuid.uuid4().hex[:8], profile=profile)
        self._sessions[session.id] = session
        return _outcome(STATUS_OK, session=session.to_dict())

    def sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._sessions.values()]

    def close_session(self, session_id: str) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return _outcome("not_found", reason=f"unknown session {session_id!r}")
        try:
            self.driver.close()
        except Exception as exc:
            session.closed = True
            return _outcome("failure", error=str(exc), session=session.to_dict())
        session.closed = True
        return _outcome(STATUS_OK, session=session.to_dict())

    def _require(self, session_id: str) -> BrowserSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown browser session {session_id!r}")
        if session.closed:
            raise KeyError(f"session {session_id} is closed")
        session.last_used = _utc()
        return session

    def active_tab(self, session_id: str) -> Dict[str, Any]:
        try:
            session = self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        try:
            tabs = list(self.driver.tabs())
        except Exception as exc:
            return _outcome("unavailable", reason=str(exc))
        session.tabs = tabs
        if session.active_tab >= len(tabs):
            session.active_tab = max(0, len(tabs) - 1)
        return _outcome(STATUS_OK, tabs=tabs, active_tab=session.active_tab,
                        url=tabs[session.active_tab] if tabs else None)

    def switch_tab(self, session_id: str, index: int) -> Dict[str, Any]:
        try:
            session = self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        try:
            tabs = list(self.driver.tabs())
            if not 0 <= int(index) < len(tabs):
                return _outcome("invalid_input",
                                reason=f"tab {index} out of range (0..{len(tabs) - 1})")
            self.driver.switch(int(index))
            after = self.driver.current_url()
        except Exception as exc:
            return _outcome("failure", error=f"{type(exc).__name__}: {exc}")
        session.active_tab = int(index)
        session.tabs = tabs
        verified = after == tabs[int(index)]
        self._log(session_id, "switch_tab", str(index), tabs[int(index)], after,
                  verified, STATUS_OK if verified else "failure")
        return _outcome(STATUS_OK if verified else "failure", active_tab=int(index),
                       url=after, verified=verified)

    # ---------------- captcha ----------------
    def detect_captcha(self, html: Optional[str] = None) -> Dict[str, Any]:
        if html is None:
            try:
                html = self.driver.page_source()
            except Exception as exc:
                return _outcome("unavailable", reason=str(exc))
        lowered = (html or "").lower()
        found = sorted({m for m in CAPTCHA_MARKERS if m in lowered})
        return _outcome(STATUS_OK, captcha=bool(found), markers=found)

    # ---------------- navigation ----------------
    def open_url(self, session_id: str, url: str) -> Dict[str, Any]:
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            return _outcome("invalid_input", reason="url must start with http:// or https://")
        try:
            self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        decision = self._guard("browser.navigate", url)
        if not decision.get("allowed"):
            return _outcome("permission_denied", reason=decision.get("reason"))
        try:
            self.driver.open(url)
            actual = self.driver.current_url()
        except Exception as exc:
            self._log(session_id, "open_url", url, url, None, False, "failure", str(exc))
            return _outcome("unavailable" if isinstance(self.driver, NullDriver) else "failure",
                            error=f"{type(exc).__name__}: {exc}")
        captcha = self.detect_captcha()
        if captcha.get("captcha"):
            self._log(session_id, "open_url", url, url, actual, False, "captcha",
                      ",".join(captcha["markers"]))
            return _outcome("captcha_required", url=actual, markers=captcha["markers"],
                            reason="CAPTCHA detected - human intervention required, "
                                   "automation stopped (bypass is never attempted)")
        verified = actual is not None
        self._log(session_id, "open_url", url, url, actual, verified, STATUS_OK)
        return _outcome(STATUS_OK, url=actual, verified=verified)

    # ---------------- forms ----------------
    def fill_form(self, session_id: str, fields: Dict[str, str],
                  submit_selector: Optional[str] = None,
                  expect_selector: Optional[str] = None,
                  expect_text: Optional[str] = None) -> Dict[str, Any]:
        """Fill fields by DOM/accessibility selector, then verify the result."""
        if not isinstance(fields, dict) or not fields:
            return _outcome("invalid_input", reason="fields must be a non-empty {selector: value} map")
        try:
            self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        decision = self._guard("browser.form", ",".join(sorted(fields)))
        if not decision.get("allowed"):
            return _outcome("permission_denied", reason=decision.get("reason"))
        pre = self.detect_captcha()
        if pre.get("captcha"):
            return _outcome("captcha_required", markers=pre["markers"],
                            reason="CAPTCHA present before submit - stopping for human")
        filled: List[str] = []
        for selector, value in fields.items():
            try:
                if not self.driver.find(selector):
                    self._log(session_id, "fill", selector, value, None, False, "not_found")
                    return _outcome("not_found", reason=f"selector {selector!r} not present",
                                    filled=filled)
                self.driver.fill(selector, value)
                actual = self.driver.text_of(selector)
            except Exception as exc:
                self._log(session_id, "fill", selector, "***" if SENSITIVE_FIELD.search(selector)
                          else value, None, False, "failure", str(exc))
                return _outcome("unavailable" if isinstance(self.driver, NullDriver) else "failure",
                                error=f"{type(exc).__name__}: {exc}", filled=filled)
            verified = actual == value
            safe = "***REDACTED***" if SENSITIVE_FIELD.search(selector) else value
            self._log(session_id, "fill", selector, safe,
                      "***REDACTED***" if SENSITIVE_FIELD.search(selector) else actual,
                      verified, STATUS_OK if verified else "failure")
            if not verified:
                return _outcome("failure", reason=f"{selector} did not accept the value",
                                filled=filled)
            filled.append(selector)
        if submit_selector:
            try:
                self.driver.click(submit_selector)
            except Exception as exc:
                self._log(session_id, "submit", submit_selector, "clicked", None, False,
                          "failure", str(exc))
                return _outcome("failure", error=f"{type(exc).__name__}: {exc}", filled=filled)
            post = self.detect_captcha()
            if post.get("captcha"):
                self._log(session_id, "submit", submit_selector, "accepted", "captcha",
                          False, "captcha")
                return _outcome("captcha_required", markers=post["markers"], filled=filled,
                                reason="CAPTCHA appeared after submit - human required")
        return self._verify_action(session_id, "fill_form", filled, expect_selector, expect_text)

    def _verify_action(self, session_id: str, action: str, filled: Any,
                       expect_selector: Optional[str],
                       expect_text: Optional[str]) -> Dict[str, Any]:
        if not expect_selector and not expect_text:
            self._log(session_id, action, str(filled), "no expectation given", "submitted",
                      False, STATUS_OK, "unverified: caller gave no expectation")
            return _outcome(STATUS_OK, filled=filled, verified=False,
                            reason="submitted, but no expectation was provided to verify against")
        try:
            actual = (self.driver.text_of(expect_selector) if expect_selector
                      else self.driver.page_source())
        except Exception as exc:
            return _outcome("failure", error=f"{type(exc).__name__}: {exc}", filled=filled)
        verified = bool(actual) and (expect_text or "") in (actual or "")
        self._log(session_id, action, str(filled), expect_text or expect_selector, actual,
                  verified, STATUS_OK if verified else "failure")
        return _outcome(STATUS_OK if verified else "failure", filled=filled, verified=verified,
                       observed=(actual or "")[:200])

    # ---------------- downloads / uploads ----------------
    def download(self, session_id: str, url: str, expected_bytes: Optional[int] = None,
                 timeout: float = 30.0, poll: float = 0.1) -> Dict[str, Any]:
        """Track a driver-initiated download to completion and verify it on disk."""
        try:
            self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        decision = self._guard("browser.download", url)
        if not decision.get("allowed"):
            return _outcome("permission_denied", reason=decision.get("reason"))
        record_id = "BD-" + uuid.uuid4().hex[:10]
        try:
            self.driver.open(url)
            deadline = time.time() + float(timeout)
            entry = None
            while time.time() < deadline:
                pending = [d for d in self.driver.downloads() if d.get("url") == url]
                if pending and pending[-1].get("state") == "completed":
                    entry = pending[-1]
                    break
                time.sleep(poll)
            if entry is None:
                self._store_download(record_id, session_id, url, None, None, "timeout",
                                     f"not completed within {timeout}s")
                return _outcome("timeout", reason=f"download did not finish within {timeout}s",
                                download_id=record_id)
        except Exception as exc:
            self._store_download(record_id, session_id, url, None, None, "failed", str(exc))
            return _outcome("unavailable" if isinstance(self.driver, NullDriver) else "failure",
                            error=f"{type(exc).__name__}: {exc}", download_id=record_id)
        path = entry.get("path")
        exists = bool(path) and os.path.isfile(path)
        size = os.path.getsize(path) if exists else None
        verified = exists and (expected_bytes is None or size == expected_bytes)
        self._store_download(record_id, session_id, url, path, size,
                             "completed" if verified else "unverified",
                             "" if verified else "file missing or size mismatch")
        self._log(session_id, "download", url, expected_bytes, size, verified,
                  STATUS_OK if verified else "failure")
        return _outcome(STATUS_OK if verified else "failure", download_id=record_id,
                       path=path, bytes=size, verified=verified)

    def _store_download(self, ident: str, session: str, url: str, path: Optional[str],
                        size: Optional[int], state: str, detail: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO browser_downloads(id, session, url, path, bytes, state, detail, at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (ident, session, url, path, size, state, detail, _utc()))
            self._conn.commit()

    def downloads(self, session: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM browser_downloads"
        params: List[Any] = []
        if session:
            sql += " WHERE session=?"
            params.append(session)
        sql += " ORDER BY at DESC, id DESC"
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def upload(self, session_id: str, selector: str, path: str) -> Dict[str, Any]:
        try:
            self._require(session_id)
        except KeyError as exc:
            return _outcome("not_found", reason=str(exc))
        if not isinstance(path, str) or not path.strip():
            return _outcome("invalid_input", reason="path must be a non-empty string")
        resolved = os.path.realpath(os.path.expanduser(path))
        if not os.path.isfile(resolved):
            return _outcome("not_found", reason=f"{resolved} is not a file")
        decision = self._guard("browser.upload", resolved)
        if not decision.get("allowed"):
            return _outcome("permission_denied", reason=decision.get("reason"))
        try:
            if not self.driver.find(selector):
                return _outcome("not_found", reason=f"upload selector {selector!r} not present")
            self.driver.upload(selector, resolved)
            attached = self.driver.text_of(selector)
        except Exception as exc:
            self._log(session_id, "upload", selector, resolved, None, False, "failure", str(exc))
            return _outcome("unavailable" if isinstance(self.driver, NullDriver) else "failure",
                            error=f"{type(exc).__name__}: {exc}")
        verified = os.path.basename(resolved) in (attached or "")
        self._log(session_id, "upload", selector, os.path.basename(resolved), attached,
                  verified, STATUS_OK if verified else "failure")
        return _outcome(STATUS_OK if verified else "failure", path=resolved,
                       attached=attached, verified=verified)

    # ---------------- manager entry point ----------------
    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        handlers = {
            "open_session": self.open_session, "close_session": self.close_session,
            "open_url": self.open_url, "fill_form": self.fill_form,
            "download": self.download, "upload": self.upload,
            "active_tab": self.active_tab, "switch_tab": self.switch_tab,
            "detect_captcha": self.detect_captcha, "health": self.health,
        }
        handler = handlers.get(action)
        if handler is None:
            return _outcome("invalid_input", reason=f"unknown browser action {action!r}",
                            supported=sorted(handlers))
        try:
            return handler(**kwargs)
        except TypeError as exc:
            return _outcome("invalid_input", reason=str(exc))


__all__ = ["BrowserManager", "BrowserDriver", "NullDriver", "BrowserSession",
           "CaptchaRequiresHuman", "CAPTCHA_MARKERS"]
