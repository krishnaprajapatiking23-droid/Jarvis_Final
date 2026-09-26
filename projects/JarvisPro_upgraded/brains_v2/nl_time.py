"""Natural-language date/time parsing for reminders and the scheduler.

BUG FIX: ``brains_v2/reminders/reminders.py:parse_time`` understood only two
shapes -- ``"in 20 minutes"`` and a bare ``"HH:MM"``. Everything people
actually say ("at 5pm", "tomorrow at 9", "tonight", "next monday",
"on 5 March") returned ``None``, and the caller then answered
"Please include a reminder time." even when a time was clearly present.

Roadmap section 8 lists "Natural-Language Dates" as a feature; this module is
that feature. Pure standard library, no new dependency.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

__all__ = ["parse_time", "strip_time_phrase"]

_UNITS = {
    "second": "seconds", "sec": "seconds", "secs": "seconds", "seconds": "seconds",
    "minute": "minutes", "min": "minutes", "mins": "minutes", "minutes": "minutes",
    "hour": "hours", "hr": "hours", "hrs": "hours", "hours": "hours",
    "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks",
}

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

# Named points in the day.
_NAMED = {
    "noon": (12, 0), "midday": (12, 0), "midnight": (0, 0),
    "morning": (9, 0), "afternoon": (14, 0), "evening": (18, 0),
    "tonight": (20, 0), "night": (20, 0),
}

_RELATIVE = re.compile(
    r"\bin\s+(?:(an?)\s+)?(\d+)?\s*"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b",
    re.IGNORECASE,
)
_CLOCK_24 = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b")
_BARE_HOUR = re.compile(r"\bat\s+(\d{1,2})\b(?!\s*[:/\-])", re.IGNORECASE)
_DAY_MONTH = re.compile(
    r"\b(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|"
    r"august|aug|september|sept|sep|october|oct|november|nov|december|dec)\b",
    re.IGNORECASE,
)
_MONTH_DAY = re.compile(
    r"\b(?:on\s+)?(january|jan|february|feb|march|mar|april|apr|may|june|jun|"
    r"july|jul|august|aug|september|sept|sep|october|oct|november|nov|"
    r"december|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?\b")
_WEEKDAY = re.compile(
    r"\b(?:(next|this)\s+)?(monday|mon|tuesday|tues|tue|wednesday|wed|"
    r"thursday|thurs|thu|friday|fri|saturday|sat|sunday|sun)\b",
    re.IGNORECASE,
)
_NAMED_RE = re.compile(
    r"\b(noon|midday|midnight|tonight|this morning|this afternoon|this evening|"
    r"morning|afternoon|evening|night)\b",
    re.IGNORECASE,
)
_TOMORROW = re.compile(r"\b(tomorrow|tmrw|day after tomorrow)\b", re.IGNORECASE)
_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)


def _clock_from(text: str):
    """Return ``(hour, minute)`` if the text names a clock time."""
    match = _CLOCK.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3).replace(".", "").lower()
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    match = _CLOCK_24.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = _NAMED_RE.search(text)
    if match:
        key = match.group(1).lower().replace("this ", "")
        if key in _NAMED:
            return _NAMED[key]

    match = _BARE_HOUR.search(text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            # "at 5" in conversation almost always means the afternoon.
            if 1 <= hour <= 7:
                hour += 12
            return hour, 0

    return None


def parse_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a due date/time out of free text, or return ``None``.

    Always returns a moment in the future for time-of-day expressions: "at 9am"
    said at 10am means tomorrow morning, not a time that has already passed.
    """
    if not text:
        return None

    now = now or datetime.now()
    lowered = str(text).lower()

    # 1. Absolute ISO timestamp.
    match = _ISO.search(lowered)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None

    # 2. Relative offset: "in 20 minutes", "in an hour".
    match = _RELATIVE.search(lowered)
    if match:
        article, amount, unit = match.group(1), match.group(2), match.group(3).lower()
        count = int(amount) if amount else (1 if article else 1)
        key = _UNITS.get(unit, _UNITS.get(unit.rstrip("s")))
        if key:
            return now + timedelta(**{key: count})

    clock = _clock_from(lowered)

    # 3. Explicit calendar date.
    day = month = None
    match = _DAY_MONTH.search(lowered)
    if match:
        day, month = int(match.group(1)), _MONTHS[match.group(2).lower()]
    else:
        match = _MONTH_DAY.search(lowered)
        if match:
            month, day = _MONTHS[match.group(1).lower()], int(match.group(2))
    if day and month:
        hour, minute = clock or (9, 0)
        try:
            due = datetime(now.year, month, day, hour, minute)
        except ValueError:
            return None
        if due <= now:
            try:
                due = due.replace(year=now.year + 1)
            except ValueError:
                return None
        return due

    # 4. Named weekday: "on friday", "next monday".
    match = _WEEKDAY.search(lowered)
    if match:
        qualifier = (match.group(1) or "").lower()
        target = _WEEKDAYS[match.group(2).lower()]
        hour, minute = clock or (9, 0)
        ahead = (target - now.weekday()) % 7
        if ahead == 0:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if qualifier == "next" or candidate <= now:
                ahead = 7
        if qualifier == "next" and ahead < 7 and (target - now.weekday()) % 7 != 0:
            pass
        due = now + timedelta(days=ahead)
        return due.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 5. today / tomorrow.
    match = _TOMORROW.search(lowered)
    if match:
        offset = 2 if match.group(1).lower().startswith("day after") else 1
        hour, minute = clock or (9, 0)
        due = now + timedelta(days=offset)
        return due.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if _TODAY.search(lowered) and clock:
        return now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)

    # 6. Bare clock time -- roll to tomorrow if it has already gone.
    if clock:
        due = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due

    return None


_TIME_PHRASES = (
    _ISO, _RELATIVE, _CLOCK, _CLOCK_24, _DAY_MONTH, _MONTH_DAY,
    _WEEKDAY, _NAMED_RE, _TOMORROW, _TODAY, _BARE_HOUR,
)


def strip_time_phrase(text: str) -> str:
    """Remove the time wording so only the task title is left."""
    cleaned = str(text or "")
    for pattern in _TIME_PHRASES:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\b(at|on|by|in)\s*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned
