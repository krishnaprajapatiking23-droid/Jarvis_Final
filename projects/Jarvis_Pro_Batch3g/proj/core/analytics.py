"""
==========================================
JARVIS PRO
Analytics & reporting
==========================================

Roadmap section 32 (analytics) and the REPORT stage of the section 42 loop.

This pulls together the numbers that are already being recorded elsewhere -
reliability from observability, outcomes from the experience store, habits from
behaviour learning, tools from the registry - and turns them into a single
readable report.

    from core.analytics import analytics

    analytics.overview()        # everything as data (for the dashboard)
    analytics.daily_report()    # readable text report
    analytics.usage()           # what gets used the most

Nothing here writes data; it only reads and summarises, so it is safe to call
from the UI at any time.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


class Analytics:
    """Read-only reporting across every JARVIS subsystem."""

    # ---------------------------------------------------- pieces

    def reliability(self) -> dict[str, Any]:
        """Success rate and failures from the observability database."""

        try:
            from core.observability import observability

            health = observability.health()
            failures = observability.failures(limit=5)

            return {
                "available": True,
                "success_rate": health.get("success_rate", 0.0),
                "events": health.get("events", 0),
                "errors": health.get("errors", 0),
                "recent_failures": [
                    {
                        "name": item.get("name", ""),
                        "detail": str(item.get("detail", ""))[:120],
                    }
                    for item in failures
                ],
            }

        except Exception as problem:
            return {"available": False, "reason": str(problem)}

    def outcomes(self) -> dict[str, Any]:
        """Task outcomes from the experience store."""

        try:
            from memory.experience import experience

            return {"available": True, **experience.stats()}

        except Exception as problem:
            return {"available": False, "reason": str(problem)}

    def usage(self, limit: int = 8) -> dict[str, Any]:
        """Which requests and tools are used most."""

        try:
            from memory.experience import experience

            records = experience.recent(400)

        except Exception:
            records = []

        requests = Counter(
            str(row.get("signature") or "").strip()
            for row in records
            if str(row.get("signature") or "").strip()
        )
        strategies = Counter(
            str(row.get("strategy") or "").strip()
            for row in records
            if str(row.get("strategy") or "").strip()
        )

        timing: dict[str, Any] = {}

        try:
            from core.observability import observability

            timing = {
                str(item.get("name", "")): item.get("average_seconds", 0)
                for item in observability.stats()[:limit]
            }

        except Exception:
            timing = {}

        return {
            "top_requests": [
                {"request": name, "times": times}
                for name, times in requests.most_common(limit)
            ],
            "strategies": [
                {"strategy": name, "times": times}
                for name, times in strategies.most_common(limit)
            ],
            "average_seconds": timing,
            "sample_size": len(records),
        }

    def activity_by_hour(self) -> dict[int, int]:
        """When during the day JARVIS is actually used."""

        try:
            from memory.experience import experience

            records = experience.recent(400)

        except Exception:
            return {}

        counts: Counter = Counter()

        for row in records:
            try:
                counts[datetime.fromtimestamp(float(row.get("at") or 0)).hour] += 1

            except Exception:
                continue

        return dict(sorted(counts.items()))

    def capabilities(self) -> dict[str, Any]:
        """How much JARVIS can currently do."""

        found: dict[str, Any] = {}

        try:
            from core.tool_schema import tool_registry

            found["tools"] = len(tool_registry.names())
            found["tool_names"] = tool_registry.names()

        except Exception:
            found["tools"] = 0
            found["tool_names"] = []

        try:
            from core.plugin_loader import plugins

            found["plugins"] = len(plugins.names())

        except Exception:
            found["plugins"] = 0

        try:
            from core.workflow_engine import workflows

            found["workflows"] = len(workflows.names())

        except Exception:
            found["workflows"] = 0

        try:
            from memory.knowledge_base import knowledge

            found["facts_known"] = knowledge.status().get("facts", 0)

        except Exception:
            found["facts_known"] = 0

        return found

    def learning(self) -> dict[str, Any]:
        """What the learning subsystems have picked up."""

        found: dict[str, Any] = {}

        try:
            from learning.behaviour import behaviour

            found["patterns"] = behaviour.patterns(limit=5)
            found["weak_spots"] = behaviour.weak_spots(limit=3)

        except Exception:
            found["patterns"] = []
            found["weak_spots"] = []

        try:
            from learning.mistakes import mistakes

            found["mistakes"] = mistakes.status()

        except Exception:
            found["mistakes"] = {}

        return found

    # ---------------------------------------------------- reports

    def overview(self) -> dict[str, Any]:
        """Everything at once - the shape the dashboard wants."""

        return {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "reliability": self.reliability(),
            "outcomes": self.outcomes(),
            "usage": self.usage(),
            "capabilities": self.capabilities(),
            "learning": self.learning(),
            "activity_by_hour": self.activity_by_hour(),
        }

    def daily_report(self) -> str:
        """A readable report suitable for chat, speech or a note."""

        data = self.overview()
        lines = [f"JARVIS report - {data['generated']}", ""]

        outcomes = data["outcomes"]

        if outcomes.get("available") and outcomes.get("attempts"):
            lines.append(
                f"Tasks: {outcomes.get('attempts', 0)} attempted, "
                f"{outcomes.get('success_rate', 0)}% successful, "
                f"averaging {outcomes.get('average_steps', 0)} steps."
            )

        else:
            lines.append("Tasks: nothing recorded yet.")

        reliability = data["reliability"]

        if reliability.get("available"):
            lines.append(
                f"Reliability: {reliability.get('success_rate', 0)}% across "
                f"{reliability.get('events', 0)} events, "
                f"{reliability.get('errors', 0)} error(s)."
            )

        capabilities = data["capabilities"]
        lines.append(
            f"Capabilities: {capabilities.get('tools', 0)} tools, "
            f"{capabilities.get('plugins', 0)} plugins, "
            f"{capabilities.get('workflows', 0)} workflows, "
            f"{capabilities.get('facts_known', 0)} facts remembered."
        )

        top = data["usage"]["top_requests"]

        if top:
            lines.append("")
            lines.append("Most used:")

            for item in top[:5]:
                lines.append(f"  - {item['request']} ({item['times']}x)")

        weak = data["learning"].get("weak_spots") or []

        if weak:
            lines.append("")
            lines.append("Needs attention:")

            for item in weak:
                lines.append(
                    f"  - {item['pattern']} fails {item['failure_rate']}% "
                    "of the time."
                )

        failures = reliability.get("recent_failures") or []

        if failures:
            lines.append("")
            lines.append("Recent errors:")

            for item in failures[:3]:
                lines.append(f"  - {item['name']}: {item['detail']}")

        return "\n".join(lines)

    def status(self) -> dict[str, Any]:
        return {
            "reliability_available": self.reliability().get("available", False),
            "outcomes_available": self.outcomes().get("available", False),
            "capabilities": self.capabilities(),
        }


analytics = Analytics()
