"""
==========================================
JARVIS PRO
Event bus
==========================================

Roadmap section 25 (event bus). This file existed in the project as an empty
stub and other modules already tried to import it, so it is now implemented.

Publish/subscribe with wildcard topics, one-shot listeners, a bounded event
history and completely isolated handlers: one broken listener can never break
the publisher or the other listeners.

    from core.event_bus import event_bus

    event_bus.subscribe("system.alert", handle_alert)
    event_bus.publish("system.alert", {"kind": "cpu", "value": 97})

Topics are dot separated. A subscription to ``system.*`` receives every
``system.<something>`` event, and ``*`` receives everything.
"""

from __future__ import annotations

import fnmatch
import threading
import time
import uuid
from typing import Any, Callable


HISTORY_LIMIT = 300


class EventBus:
    """Thread-safe publish/subscribe hub."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: dict[str, list[dict[str, Any]]] = {}
        self._history: list[dict[str, Any]] = []

    # ---------------------------------------------------- subscribing

    def subscribe(
        self,
        topic: str,
        handler: Callable[..., Any],
        once: bool = False,
    ) -> str:
        """Register a handler and return an id you can unsubscribe with."""

        if not callable(handler):
            raise TypeError("event handler must be callable")

        pattern = str(topic or "*").strip() or "*"
        listener_id = uuid.uuid4().hex[:10]

        with self._lock:
            self._listeners.setdefault(pattern, []).append(
                {"id": listener_id, "handler": handler, "once": bool(once)}
            )

        return listener_id

    def once(self, topic: str, handler: Callable[..., Any]) -> str:
        return self.subscribe(topic, handler, once=True)

    def unsubscribe(self, listener_id: str) -> bool:
        with self._lock:
            for pattern, listeners in list(self._listeners.items()):
                for listener in list(listeners):
                    if listener["id"] == listener_id:
                        listeners.remove(listener)

                        if not listeners:
                            self._listeners.pop(pattern, None)

                        return True

        return False

    def clear(self, topic: str | None = None) -> None:
        with self._lock:
            if topic is None:
                self._listeners.clear()

            else:
                self._listeners.pop(topic, None)

    # ---------------------------------------------------- publishing

    def _matching(self, topic: str) -> list[dict[str, Any]]:
        with self._lock:
            matched: list[dict[str, Any]] = []

            for pattern, listeners in self._listeners.items():
                if pattern == topic or fnmatch.fnmatch(topic, pattern):
                    matched.extend(listeners)

            return matched

    def publish(self, topic: str, payload: Any = None) -> dict[str, Any]:
        """Send an event. Never raises, whatever the listeners do."""

        name = str(topic or "").strip()

        if not name:
            return {"topic": "", "delivered": 0, "failed": 0}

        event = {"topic": name, "payload": payload, "at": time.time()}

        with self._lock:
            self._history.append(event)
            del self._history[:-HISTORY_LIMIT]

        delivered = 0
        failed = 0

        for listener in self._matching(name):
            try:
                handler = listener["handler"]

                try:
                    handler(payload)

                except TypeError:
                    handler()

                delivered += 1

            except Exception as failure:
                failed += 1

                try:
                    from core.observability import observability

                    observability.warn(
                        f"event listener failed for {name}: {failure}"
                    )

                except Exception:
                    pass

            finally:
                if listener["once"]:
                    self.unsubscribe(listener["id"])

        return {"topic": name, "delivered": delivered, "failed": failed}

    # emit is a common alias in the rest of the project
    emit = publish

    def publish_async(self, topic: str, payload: Any = None) -> None:
        """Fire and forget - useful for slow listeners."""

        threading.Thread(
            target=self.publish,
            args=(topic, payload),
            name="jarvis-event",
            daemon=True,
        ).start()

    # ---------------------------------------------------- inspection

    def topics(self) -> list[str]:
        with self._lock:
            return sorted(self._listeners)

    def listener_count(self, topic: str | None = None) -> int:
        if topic is None:
            with self._lock:
                return sum(len(items) for items in self._listeners.values())

        return len(self._matching(topic))

    def history(self, topic: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._history)

        if topic:
            events = [
                event
                for event in events
                if event["topic"] == topic
                or fnmatch.fnmatch(event["topic"], topic)
            ]

        return events[-limit:]

    def wait_for(self, topic: str, timeout: float = 10.0) -> Any:
        """Block until an event arrives on the topic. Returns its payload."""

        box: dict[str, Any] = {}
        arrived = threading.Event()

        def catch(payload: Any = None) -> None:
            box["payload"] = payload
            arrived.set()

        listener_id = self.subscribe(topic, catch, once=True)

        try:
            if arrived.wait(timeout=timeout):
                return box.get("payload")

            return None

        finally:
            self.unsubscribe(listener_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "patterns": sorted(self._listeners),
                "listeners": sum(len(items) for items in self._listeners.values()),
                "events_recorded": len(self._history),
            }


event_bus = EventBus()

# short aliases used by different parts of the project
bus = event_bus


def publish(topic: str, payload: Any = None) -> dict[str, Any]:
    return event_bus.publish(topic, payload)


def subscribe(topic: str, handler: Callable[..., Any]) -> str:
    return event_bus.subscribe(topic, handler)
