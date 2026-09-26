"""
Event Bus — a lightweight pub/sub system for internal JARVIS events.

Usage:
    from event_bus.bus import emit, on, once

    on("command_executed", my_handler)
    emit("command_executed", {"command": "open notepad"})
"""

from collections import defaultdict
from threading import Lock
from typing import Callable, Dict, List, Any


class EventBus:
    """Thread-safe publish/subscribe event bus."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._once: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Dict] = []
        self._lock = Lock()
        self._max_history = 100

    def on(self, event: str, handler: Callable) -> None:
        """Subscribe a handler to an event (persistent)."""
        with self._lock:
            self._listeners[event].append(handler)

    def once(self, event: str, handler: Callable) -> None:
        """Subscribe a handler to an event (fires once, then removed)."""
        with self._lock:
            self._once[event].append(handler)

    def off(self, event: str, handler: Callable = None) -> None:
        """Unsubscribe a handler, or all handlers if none given."""
        with self._lock:
            if handler is None:
                self._listeners.pop(event, None)
                self._once.pop(event, None)
            else:
                if handler in self._listeners.get(event, []):
                    self._listeners[event].remove(handler)
                if handler in self._once.get(event, []):
                    self._once[event].remove(handler)

    def emit(self, event: str, data: Any = None) -> List[Any]:
        """Publish an event and return a list of handler return values."""
        with self._lock:
            all_handlers = (
                self._listeners.get(event, [])
                + self._once.get(event, [])
            )
            self._once.pop(event, None)  # clear once handlers

            entry = {"event": event, "data": data}
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history.pop(0)

        results = []
        for handler in all_handlers:
            try:
                results.append(handler(data))
            except Exception as e:
                results.append({"error": str(e)})
        return results

    def history(self, limit: int = 20) -> List[Dict]:
        """Return recent event history."""
        return self._history[-limit:]

    def listeners(self, event: str = None) -> Dict[str, int]:
        """Return listener counts, optionally for a specific event."""
        if event:
            return {event: len(self._listeners.get(event, []))}
        return {e: len(v) for e, v in self._listeners.items()}


_bus = EventBus()

on = _bus.on
once = _bus.once
off = _bus.off
emit = _bus.emit
history = _bus.history
listeners = _bus.listeners
