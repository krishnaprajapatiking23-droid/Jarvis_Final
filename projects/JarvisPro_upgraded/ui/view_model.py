"""Dashboard view model (deep-spec section 10/14).

This is the layer the screenshot maps onto: gauges, arc reactor, system info,
activity feed, reminders, notes, tasks, quick actions and modes. It reads from
the kernel and the telemetry provider and never invents a value - a panel that
cannot be read comes back as UNAVAILABLE or NOT_CONFIGURED with a reason.
"""

import time
from typing import Any, Dict, List, Optional

from .settings import MODES
from .telemetry import TelemetryProvider, format_duration, host_info

OK = "ok"
INVALID = "invalid_input"
UNAVAILABLE = "UNAVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"

PAGES = ("dashboard", "chat", "voice", "automation", "memory", "files",
         "system", "settings", "about")

QUICK_ACTIONS = (
    {"id": "open_chat", "label": "Open Chat", "page": "chat"},
    {"id": "voice", "label": "Voice Command", "page": "voice"},
    {"id": "new_note", "label": "New Note", "page": "memory"},
    {"id": "new_reminder", "label": "New Reminder", "page": "memory"},
    {"id": "run_automation", "label": "Run Automation", "page": "automation"},
    {"id": "open_browser", "label": "Open Browser", "page": "automation"},
    {"id": "system_scan", "label": "System Scan", "page": "system"},
    {"id": "file_search", "label": "File Search", "page": "files"},
    {"id": "settings", "label": "Settings", "page": "settings"},
)

VOICE_EXAMPLES = (
    "Jarvis, what is my system status?",
    "Jarvis, remind me to revise physics at 8 pm",
    "Jarvis, open my notes",
    "Jarvis, search the web for JEE syllabus",
    "Jarvis, run my study automation",
)

GREETING = "Hello %s, how can I help you today?"


def _panel(status: str, **extra: Any) -> Dict[str, Any]:
    out = {"status": status, "reason": None}
    out.update(extra)
    return out


class DashboardViewModel:
    capability = "ui_dashboard"

    def __init__(self, kernel: Any = None,
                 telemetry: Optional[TelemetryProvider] = None,
                 settings: Any = None, owner: Optional[str] = None) -> None:
        self.kernel = kernel
        self.telemetry = telemetry or TelemetryProvider()
        self.settings = settings
        self.owner = owner or (settings.get("owner_name") if settings else "the owner")
        self.page = (settings.get("start_page") if settings else "dashboard")
        self._mode = (settings.get("mode") if settings else "standard")
        self.started = time.time()
        self.refreshes = 0
        self._last: Optional[Dict[str, Any]] = None
        self._host = host_info()

    # ---- navigation / modes ----
    def navigate(self, page: str) -> Dict[str, Any]:
        if page not in PAGES:
            return {"status": INVALID,
                    "error": "unknown page %r; expected one of %s"
                             % (page, ", ".join(PAGES))}
        self.page = page
        return {"status": OK, "page": page}

    def set_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in MODES:
            return {"status": INVALID,
                    "error": "mode must be one of %s" % ", ".join(MODES)}
        if self.settings is not None:
            result = self.settings.set("mode", mode)
            if result.get("status") != OK:
                return result
        self._mode = mode
        return {"status": OK, "mode": mode}

    def mode(self) -> str:
        if self.settings is not None:
            return self.settings.get("mode") or self._mode
        return self._mode

    # ---- panels ----
    def _kernel_state(self) -> Dict[str, Any]:
        if self.kernel is None:
            return {"status": NOT_CONFIGURED, "managers": {}, "degraded": [],
                    "reason": "no kernel attached to the UI"}
        reader = getattr(self.kernel, "status", None) or getattr(
            self.kernel, "health", None)
        if reader is None:
            return {"status": NOT_CONFIGURED, "managers": {}, "degraded": [],
                    "reason": "kernel exposes no status surface"}
        try:
            raw = reader() or {}
        except Exception as exc:
            return {"status": UNAVAILABLE, "managers": {}, "degraded": [],
                    "reason": "kernel status failed: %s" % exc}
        managers = raw.get("managers") or {}
        if isinstance(managers, dict) and "managers" in managers:
            managers = managers.get("managers") or {}
        degraded = []
        if isinstance(managers, dict):
            for name, info in managers.items():
                if isinstance(info, dict) and info.get("available") is False:
                    degraded.append(name)
        return {"status": OK, "managers": managers,
                "degraded": sorted(degraded), "raw": raw, "reason": None}

    def header(self, sample: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sample = sample or self.telemetry.sample()
        gauges = {}
        for name in ("cpu", "memory", "storage", "battery"):
            metric = (sample.get("metrics") or {}).get(name) or {}
            gauges[name] = {"value": metric.get("value"),
                            "unit": metric.get("unit", "%"),
                            "status": metric.get("status", UNAVAILABLE),
                            "reason": metric.get("reason")}
        return {"status": OK, "owner": self.owner, "gauges": gauges,
                "mode": self.mode(), "page": self.page,
                "degraded": sample.get("degraded", [])}

    def reactor(self, sample: Optional[Dict[str, Any]] = None,
                kernel_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sample = sample or self.telemetry.sample()
        state = kernel_state or self._kernel_state()
        degraded = sorted(set(list(state.get("degraded", []))
                              + list(sample.get("degraded", []))))
        online = state.get("status") == OK and not state.get("degraded")
        return {"status": OK,
                "state": "ONLINE" if online else "OFFLINE",
                "greeting": GREETING % self.owner,
                "degraded": degraded,
                "reason": state.get("reason"),
                "session_uptime": format_duration(time.time() - self.started)}

    def system_info(self, sample: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sample = sample or self.telemetry.sample()
        metrics = sample.get("metrics") or {}
        network = metrics.get("network") or {}
        uptime = metrics.get("uptime") or {}
        data = dict(self._host)
        data.update({"local_ip": network.get("local_ip"),
                     "latency_ms": network.get("value"),
                     "network_status": network.get("status"),
                     "network_reason": network.get("reason"),
                     "host_uptime": uptime.get("pretty"),
                     "session_uptime": format_duration(time.time() - self.started)})
        return {"status": OK, "data": data}

    def _from_kernel(self, attribute: str, call: str,
                     limit: Optional[int] = None) -> Dict[str, Any]:
        target = getattr(self.kernel, attribute, None) if self.kernel else None
        if target is None:
            return _panel(NOT_CONFIGURED, items=[],
                          reason="%s is not wired into this kernel" % attribute)
        method = getattr(target, call, None)
        if method is None:
            return _panel(NOT_CONFIGURED, items=[],
                          reason="%s has no %s()" % (attribute, call))
        try:
            items = method(limit) if limit is not None else method()
        except Exception as exc:
            return _panel(UNAVAILABLE, items=[],
                          reason="%s.%s failed: %s" % (attribute, call, exc))
        if isinstance(items, dict):
            return _panel(OK, items=[items], data=items)
        return _panel(OK, items=list(items or []))

    def activity(self, limit: int = 8) -> Dict[str, Any]:
        target = getattr(self.kernel, "observability", None) if self.kernel else None
        if target is None:
            return _panel(NOT_CONFIGURED, items=[],
                          reason="observability is not wired into this kernel")
        for call in ("recent_events", "recent", "events"):
            method = getattr(target, call, None)
            if method is None:
                continue
            try:
                events = method(limit)
            except Exception as exc:
                return _panel(UNAVAILABLE, items=[],
                              reason="activity feed unavailable: %s" % exc)
            rows = []
            for event in list(events or [])[:limit]:
                if isinstance(event, dict):
                    rows.append({"component": event.get("component"),
                                 "operation": event.get("operation"),
                                 "status": event.get("status"),
                                 "at": event.get("timestamp") or event.get("at")})
                else:
                    rows.append({"component": "event", "operation": str(event),
                                 "status": OK, "at": None})
            return _panel(OK, items=rows)
        return _panel(NOT_CONFIGURED, items=[],
                      reason="observability exposes no event reader")

    def reminders(self, limit: int = 5) -> Dict[str, Any]:
        return self._from_kernel("reminders", "due")

    def notes(self, limit: int = 5) -> Dict[str, Any]:
        panel = self._from_kernel("notes", "recent", limit)
        if panel["status"] == NOT_CONFIGURED:
            panel = self._from_kernel("notes", "list")
        return panel

    def tasks(self) -> Dict[str, Any]:
        return self._from_kernel("tasks", "summary")

    def quick_actions(self) -> List[Dict[str, Any]]:
        return [dict(action) for action in QUICK_ACTIONS]

    def voice_examples(self) -> List[str]:
        return list(VOICE_EXAMPLES)

    # ---- composition ----
    def refresh(self) -> Dict[str, Any]:
        """Build the whole dashboard. Never raises: the UI must still paint."""
        try:
            sample = self.telemetry.sample()
        except Exception as exc:
            sample = {"metrics": {}, "degraded": ["telemetry"],
                      "reason": str(exc)}
        state = self._kernel_state()
        snapshot = {
            "status": OK,
            "at": time.time(),
            "page": self.page,
            "owner": self.owner,
            "header": self.header(sample),
            "reactor": self.reactor(sample, state),
            "system": self.system_info(sample),
            "activity": self.activity(),
            "reminders": self.reminders(),
            "notes": self.notes(),
            "tasks": self.tasks(),
            "quick_actions": self.quick_actions(),
            "voice_examples": self.voice_examples(),
            "modes": {"active": self.mode(), "options": list(MODES)},
        }
        degraded = sorted(set(snapshot["reactor"]["degraded"]))
        for name in ("activity", "reminders", "notes", "tasks"):
            if snapshot[name]["status"] != OK:
                degraded.append(name)
        snapshot["degraded"] = sorted(set(degraded))
        self.refreshes += 1
        self._last = snapshot
        return snapshot

    def last(self) -> Optional[Dict[str, Any]]:
        return self._last

    def health(self) -> Dict[str, Any]:
        return {"available": True, "status": OK, "page": self.page,
                "mode": self.mode(), "refreshes": self.refreshes,
                "owner": self.owner,
                "degraded": (self._last or {}).get("degraded", [])}
