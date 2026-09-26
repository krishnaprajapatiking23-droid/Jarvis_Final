"""Non-blocking notification centre (deep-spec section 15).

Toasts never block the UI: pushing one only queues it. The centre caps how
many are visible, de-duplicates repeats, expires them on time, and lets a more
severe toast displace a milder one that is already on screen.
"""

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

OK = "ok"
INVALID = "invalid_input"
NOT_FOUND = "not_found"

LEVELS = ("info", "success", "warning", "error")
_LEVEL_RANK = {"info": 0, "success": 1, "warning": 2, "error": 3}

MAX_VISIBLE = 3
MAX_QUEUE = 200
DEFAULT_TTL = 6.0
DEDUPE_WINDOW = 10.0
MAX_BODY_CHARS = 400


def new_toast_id() -> str:
    return "TST-%s" % uuid.uuid4().hex[:8]


class ToastCenter:
    capability = "ui_toasts"

    def __init__(self, max_visible: int = MAX_VISIBLE,
                 max_queue: int = MAX_QUEUE,
                 default_ttl: float = DEFAULT_TTL,
                 dedupe_window: float = DEDUPE_WINDOW) -> None:
        self.max_visible = max(1, int(max_visible))
        self.max_queue = max(1, int(max_queue))
        self.default_ttl = float(default_ttl)
        self.dedupe_window = float(dedupe_window)
        self._lock = threading.RLock()
        self._queue: List[Dict[str, Any]] = []
        self._visible: List[Dict[str, Any]] = []
        self._history: List[Dict[str, Any]] = []
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self.shown = 0
        self.duplicates = 0
        self.dropped = 0
        self.displaced = 0

    def on_show(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append(callback)

    # ---- push ----
    def push(self, title: Any, body: str = "", level: str = "info",
             action: Optional[str] = None, ttl: Optional[float] = None,
             now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else float(now)
        if not isinstance(title, str) or not title.strip():
            return {"status": INVALID, "error": "a toast needs a title"}
        if level not in LEVELS:
            return {"status": INVALID,
                    "error": "level must be one of %s" % ", ".join(LEVELS)}
        body = (body or "")[:MAX_BODY_CHARS]
        key = "%s|%s|%s" % (level, title.strip(), body)
        with self._lock:
            for entry in self._visible + self._queue:
                if entry["key"] == key and now - entry["created"] <= self.dedupe_window:
                    entry["count"] += 1
                    self.duplicates += 1
                    return {"status": OK, "id": entry["id"], "level": level,
                            "duplicate": True, "count": entry["count"]}
            toast = {"id": new_toast_id(), "title": title.strip(), "body": body,
                     "level": level, "action": action, "created": now,
                     "count": 1,
                     "ttl": float(ttl if ttl is not None else self.default_ttl),
                     "expires": now + float(ttl if ttl is not None
                                            else self.default_ttl),
                     "dismissed": False, "shown_at": None, "key": key}
            dropped_self = False
            if len(self._queue) >= self.max_queue:
                mildest = min(self._queue,
                              key=lambda t: (_LEVEL_RANK[t["level"]],
                                             -t["created"]))
                if _LEVEL_RANK[level] > _LEVEL_RANK[mildest["level"]]:
                    self._queue = [t for t in self._queue
                                   if t["id"] != mildest["id"]]
                    self.dropped += 1
                    self._queue.append(toast)
                else:
                    self.dropped += 1
                    dropped_self = True
            else:
                self._queue.append(toast)
        self._promote(now)
        result = {"status": OK, "id": toast["id"], "level": level,
                  "queued": not dropped_self}
        if dropped_self:
            result["dropped"] = True
            result["reason"] = "notification queue is full of equal or higher priority items"
        return result

    def _promote(self, now: float) -> None:
        with self._lock:
            self._visible = [t for t in self._visible
                             if not t["dismissed"] and t["expires"] > now]
            self._queue.sort(key=lambda t: (-_LEVEL_RANK[t["level"]], t["created"]))
            while self._queue and len(self._visible) < self.max_visible:
                self._show(self._queue.pop(0), now)
            # A more severe toast must not wait behind milder ones already on
            # screen: it displaces the mildest visible toast.
            while self._queue and self._visible:
                incoming = self._queue[0]
                mildest = min(self._visible,
                              key=lambda t: (_LEVEL_RANK[t["level"]],
                                             -t["created"]))
                if _LEVEL_RANK[incoming["level"]] <= _LEVEL_RANK[mildest["level"]]:
                    break
                mildest["dismissed"] = True
                self._visible = [t for t in self._visible
                                 if t["id"] != mildest["id"]]
                self._show(self._queue.pop(0), now)
                self.displaced += 1
            if len(self._history) > self.max_queue:
                del self._history[0:len(self._history) - self.max_queue]

    def _show(self, toast: Dict[str, Any], now: float) -> None:
        toast["shown_at"] = now
        toast["expires"] = now + toast["ttl"]
        self._visible.append(toast)
        self._history.append(dict(toast))
        self.shown += 1
        for listener in list(self._listeners):
            try:
                listener(dict(toast))
            except Exception:
                pass  # a broken renderer must not lose the notification

    # ---- reads / control ----
    def visible(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        now = time.time() if now is None else float(now)
        self._promote(now)
        with self._lock:
            return [{k: v for k, v in t.items() if k != "key"}
                    for t in self._visible]

    def dismiss(self, toast_id: str,
                now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else float(now)
        with self._lock:
            for entry in self._visible + self._queue:
                if entry["id"] == toast_id:
                    entry["dismissed"] = True
                    entry["expires"] = now
                    break
            else:
                return {"status": NOT_FOUND, "id": toast_id}
            self._queue = [t for t in self._queue if t["id"] != toast_id]
        self._promote(now)
        return {"status": OK, "id": toast_id}

    def clear(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else float(now)
        with self._lock:
            cleared = len(self._visible) + len(self._queue)
            self._visible.clear()
            self._queue.clear()
        return {"status": OK, "cleared": cleared, "at": now}

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [{k: v for k, v in t.items() if k != "key"}
                    for t in self._history[-int(max(1, limit)):]][::-1]

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {"available": True, "status": OK,
                    "visible": len(self._visible), "queued": len(self._queue),
                    "shown": self.shown, "duplicates": self.duplicates,
                    "dropped": self.dropped, "displaced": self.displaced,
                    "max_visible": self.max_visible}
