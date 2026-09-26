"""
Analytics Engine — collects, aggregates, and reports usage statistics.

Metrics tracked:
  - Commands per session / all time
  - Intent distribution
  - Response time percentiles
  - Success/failure rates
  - Peak usage hours
  - Most-used features
"""

import json
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Dict, List


_DATA_FILE = Path(__file__).parent / "data" / "analytics.json"


class AnalyticsEngine:

    def __init__(self):
        self._events: List[Dict] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._lock = Lock()
        self._session_start = time.time()
        self._load()

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def track(self, event_type: str, data: Dict = None) -> None:
        """Record an analytics event."""
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "data": data or {},
        }
        with self._lock:
            self._events.append(entry)
            self._counters[event_type] += 1
            self._save()

    def track_command(self, command: str, intent: str,
                     duration_ms: float, success: bool) -> None:
        self.track("command", {
            "command": command[:80],
            "intent": intent,
            "duration_ms": duration_ms,
            "success": success,
        })

    def track_error(self, error: str, context: str = "") -> None:
        self.track("error", {"error": error, "context": context})

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def report(self, since: float = None) -> Dict:
        """Return a full analytics report."""
        with self._lock:
            events = self._events if since is None else \
                [e for e in self._events if e["ts"] >= since]

        total = len(events)
        if total == 0:
            return {
                "total_events": 0,
                "session_duration_s": round(
                    time.time() - self._session_start, 1),
                "counters": dict(self._counters),
                "top_intents": [],
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
            }

        # Intent breakdown
        intent_counts: Dict[str, int] = defaultdict(int)
        durations: List[float] = []
        successes = 0
        errors = 0

        for e in events:
            d = e.get("data", {})
            if e["type"] == "command":
                intent_counts[d.get("intent", "unknown")] += 1
                durations.append(d.get("duration_ms", 0))
                if d.get("success"):
                    successes += 1
                else:
                    errors += 1
            elif e["type"] == "error":
                errors += 1

        durations.sort()
        p50 = durations[len(durations) // 2] if durations else 0
        p95 = durations[int(len(durations) * 0.95)] if durations else 0

        return {
            "total_events": total,
            "session_duration_s": round(
                time.time() - self._session_start, 1),
            "counters": dict(self._counters),
            "top_intents": sorted(intent_counts.items(),
                                  key=lambda x: -x[1])[:10],
            "success_rate": round(
                successes / (successes + errors), 3) if (successes + errors) > 0 else 0,
            "error_count": errors,
            "avg_duration_ms": round(
                sum(durations) / len(durations), 1) if durations else 0,
            "p50_duration_ms": p50,
            "p95_duration_ms": p95,
        }

    def intent_distribution(self) -> Dict[str, float]:
        """Return normalised intent percentages."""
        with self._lock:
            events = [e for e in self._events if e["type"] == "command"]
        counts: Dict[str, int] = defaultdict(int)
        for e in events:
            counts[e.get("data", {}).get("intent", "unknown")] += 1
        total = sum(counts.values())
        if total == 0:
            return {}
        return {k: round(v / total, 3) for k, v in counts.items()}

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._counters.clear()
            self._session_start = time.time()
            self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            if _DATA_FILE.exists():
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self._events = raw.get("events", [])
                    self._counters = defaultdict(
                        int, raw.get("counters", {}))
        except Exception:
            pass

    def _save(self):
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"events": self._events, "counters": dict(self._counters)},
                    f, ensure_ascii=False, indent=2)
        except Exception:
            pass


_engine = AnalyticsEngine()

track = _engine.track
track_command = _engine.track_command
track_error = _engine.track_error
report = _engine.report
intent_distribution = _engine.intent_distribution
reset = _engine.reset
