"""
==========================================
JARVIS PRO
Temporal Parser  (feature 3.22)
==========================================

Turns natural time references into structured data that automation and
the scheduler can consume.

All resolution uses the machine's LOCAL time (``datetime.now()``), never
UTC, so "tomorrow morning" means tomorrow morning where the user is.

Result shape::

    {
        "text": "tomorrow morning",
        "kind": "date" | "datetime" | "duration" | "vague",
        "start": "2026-09-10T09:00:00",
        "date": "2026-09-10",
        "time": "09:00",
        "seconds": 0,
        "granularity": "day" | "time" | "week" | "vague",
        "direction": "future" | "past" | "present",
    }
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.conversation.temporal")

# Named parts of the day -> representative hour.
DAY_PARTS: Dict[str, int] = {
    "morning": 9,
    "noon": 12,
    "afternoon": 15,
    "evening": 18,
    "night": 21,
    "tonight": 21,
    "midnight": 0,
}

WEEKDAYS: Dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

UNIT_SECONDS: Dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
    "day": 86400,
    "days": 86400,
    "week": 604800,
    "weeks": 604800,
}

NUMBER_WORDS: Dict[str, int] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45, "sixty": 60,
    "half": 0,
}

VAGUE: Dict[str, str] = {
    "later": "future",
    "soon": "future",
    "sometime": "future",
    "in a while": "future",
    "earlier": "past",
    "recently": "past",
    "last time": "past",
    "previously": "past",
    "the other day": "past",
    "just now": "past",
    "next time": "future",
    "a while ago": "past",
    "just now": "past",
    "before": "past",
    "now": "present",
    "right now": "present",
    "immediately": "present",
}

_DURATION = re.compile(
    r"\b(?:in|after|within|for)\s+(\d+|a|an|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|fifteen|twenty|thirty|half)\s*"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b"
)

_CLOCK = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b"
    r"|\bat\s+(\d{1,2}):(\d{2})\b"
)

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _result(
    text: str,
    kind: str,
    moment: Optional[datetime] = None,
    seconds: int = 0,
    granularity: str = "day",
    direction: str = "future",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "text": text,
        "kind": kind,
        "start": _iso(moment) if moment else None,
        "date": moment.strftime("%Y-%m-%d") if moment else None,
        "time": moment.strftime("%H:%M") if moment and granularity == "time" else None,
        "seconds": seconds,
        "granularity": granularity,
        "direction": direction,
    }
    return payload


class TemporalParser:
    """Parses time references relative to local system time."""

    def now(self) -> datetime:
        """Overridable clock (tests patch this instead of the module)."""
        return datetime.now()

    # ------------------------------------------------------------------
    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        """Return the strongest time reference in ``text``, or None."""
        found = self.parse_all(text)
        return found[0] if found else None

    def parse_all(self, text: str) -> List[Dict[str, Any]]:
        """Return every recognised time reference, most specific first."""
        if not text or not text.strip():
            return []

        try:
            return self._parse_all(text)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("temporal parsing failed for %r: %s", text, error)
            return []

    # ------------------------------------------------------------------
    def _parse_all(self, text: str) -> List[Dict[str, Any]]:
        lowered = text.lower()
        now = self.now()
        results: List[Dict[str, Any]] = []

        duration = self._duration(lowered, now)
        if duration:
            results.append(duration)

        explicit = self._explicit_date(lowered, now)
        if explicit:
            results.append(explicit)

        day = self._relative_day(lowered, now)
        clock = self._clock(lowered, now, day)
        if clock:
            results.append(clock)
        elif day:
            results.append(day)

        # "JARVIS yesterday, testing today, Python tomorrow": keep every
        # mention so each activity can be lined up with its own day.
        for extra in self._all_relative_days(lowered, now):
            if not any(item.get("text") == extra["text"] for item in results):
                results.append(extra)

        week = self._relative_week(lowered, now)
        if week:
            results.append(week)

        weekday = self._weekday(lowered, now)
        if weekday:
            results.append(weekday)

        if not results:
            vague = self._vague(lowered, now)
            if vague:
                results.append(vague)

        ranking = {"datetime": 0, "duration": 1, "date": 2, "vague": 3}
        results.sort(key=lambda item: ranking.get(item["kind"], 9))
        return results

    # ------------------------------------------------------------------
    def _duration(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        match = _DURATION.search(lowered)
        if not match:
            return None

        raw_amount, raw_unit = match.group(1), match.group(2)
        amount = (
            int(raw_amount)
            if raw_amount.isdigit()
            else NUMBER_WORDS.get(raw_amount, 1)
        )
        unit = UNIT_SECONDS.get(raw_unit, UNIT_SECONDS.get(raw_unit.rstrip("s"), 60))
        if raw_amount == "half":
            seconds = unit // 2
        else:
            seconds = amount * unit

        return _result(
            match.group(0).strip(),
            "duration",
            moment=now + timedelta(seconds=seconds),
            seconds=seconds,
            granularity="time",
        )

    # ------------------------------------------------------------------
    def _explicit_date(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        match = _ISO_DATE.search(lowered)
        if not match:
            return None
        try:
            moment = datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
        except ValueError:
            return None
        return _result(
            match.group(0),
            "date",
            moment=moment,
            granularity="day",
            direction="future" if moment.date() >= now.date() else "past",
        )

    # ------------------------------------------------------------------
    def _relative_day(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        offsets = (
            ("day after tomorrow", 2),
            ("day before yesterday", -2),
            ("tomorrow", 1),
            ("yesterday", -1),
            ("today", 0),
            ("tonight", 0),
        )
        for phrase, offset in offsets:
            if phrase in lowered:
                moment = (now + timedelta(days=offset)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                direction = (
                    "present" if offset == 0 else "future" if offset > 0 else "past"
                )
                if phrase == "tonight":
                    moment = moment.replace(hour=DAY_PARTS["night"])
                    return _result(
                        phrase, "datetime", moment, granularity="time",
                        direction=direction,
                    )
                return _result(
                    phrase, "date", moment, granularity="day", direction=direction
                )
        return None

    # ------------------------------------------------------------------
    def _all_relative_days(
        self, lowered: str, now: datetime
    ) -> List[Dict[str, Any]]:
        """Every yesterday/today/tomorrow mention, in reading order."""
        offsets = (
            ("day after tomorrow", 2),
            ("day before yesterday", -2),
            ("tomorrow", 1),
            ("yesterday", -1),
            ("today", 0),
        )

        remaining = lowered
        found = []

        for phrase, offset in offsets:
            position = remaining.find(phrase)
            if position < 0:
                continue
            # Blank the match so "tomorrow" does not fire again inside
            # "day after tomorrow".
            remaining = remaining.replace(phrase, " " * len(phrase))
            found.append((position, phrase, offset))

        found.sort(key=lambda item: item[0])

        results: List[Dict[str, Any]] = []

        for _, phrase, offset in found:
            moment = (now + timedelta(days=offset)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if offset == 0:
                direction = "present"
            elif offset > 0:
                direction = "future"
            else:
                direction = "past"
            results.append(
                _result(
                    phrase,
                    "date",
                    moment,
                    granularity="day",
                    direction=direction,
                )
            )

        return results

    # ------------------------------------------------------------------
    def _clock(
        self, lowered: str, now: datetime, day: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        base = now
        label_prefix = ""
        if day and day.get("date"):
            base = datetime.fromisoformat(str(day["start"]))
            label_prefix = f"{day['text']} "

        match = _CLOCK.search(lowered)
        if match:
            if match.group(1):
                hour = int(match.group(1))
                minute = int(match.group(2) or 0)
                meridiem = (match.group(3) or "").replace(".", "")
                if meridiem.startswith("p") and hour < 12:
                    hour += 12
                if meridiem.startswith("a") and hour == 12:
                    hour = 0
            else:
                hour = int(match.group(4))
                minute = int(match.group(5))

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                moment = base.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if not day and moment < now:
                    moment += timedelta(days=1)
                return _result(
                    f"{label_prefix}{match.group(0).strip()}".strip(),
                    "datetime",
                    moment,
                    granularity="time",
                )

        for part, hour in DAY_PARTS.items():
            if part == "tonight":
                continue
            if re.search(rf"\b(?:this |tomorrow |yesterday )?{part}\b", lowered):
                moment = base.replace(hour=hour, minute=0, second=0, microsecond=0)
                if not day and moment < now and "this" not in lowered:
                    moment += timedelta(days=1)
                return _result(
                    f"{label_prefix}{part}".strip(),
                    "datetime",
                    moment,
                    granularity="time",
                    direction=day["direction"] if day else "future",
                )
        return None

    # ------------------------------------------------------------------
    def _relative_week(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        options = (
            ("next week", 7, "future"),
            ("last week", -7, "past"),
            ("this week", 0, "present"),
            ("next month", 30, "future"),
            ("last month", -30, "past"),
            ("next year", 365, "future"),
            ("last year", -365, "past"),
        )
        for phrase, offset, direction in options:
            if phrase in lowered:
                moment = (now + timedelta(days=offset)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                return _result(
                    phrase, "date", moment, granularity="week", direction=direction
                )
        return None

    # ------------------------------------------------------------------
    def _weekday(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        for name, index in WEEKDAYS.items():
            if not re.search(rf"\b{name}\b", lowered):
                continue
            past = "last" in lowered
            delta = (index - now.weekday()) % 7
            if past:
                delta = -((now.weekday() - index) % 7 or 7)
            elif delta == 0:
                delta = 7 if "next" in lowered else 0
            moment = (now + timedelta(days=delta)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return _result(
                name,
                "date",
                moment,
                granularity="day",
                direction="past" if past else "future",
            )
        return None

    # ------------------------------------------------------------------
    def _vague(self, lowered: str, now: datetime) -> Optional[Dict[str, Any]]:
        for phrase in sorted(VAGUE, key=len, reverse=True):
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                direction = VAGUE[phrase]
                return _result(
                    phrase,
                    "vague",
                    moment=now if direction == "present" else None,
                    granularity="vague",
                    direction=direction,
                )
        return None

    # ------------------------------------------------------------------
    def has_time_reference(self, text: str) -> bool:
        return bool(self.parse(text))


temporal_parser = TemporalParser()

__all__ = ["TemporalParser", "temporal_parser", "DAY_PARTS", "WEEKDAYS"]
