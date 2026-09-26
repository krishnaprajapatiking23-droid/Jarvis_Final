"""
==========================================
JARVIS PRO
Application automation
==========================================

Changes made during the conversation-system repair:

* ``match_app()`` was extracted so the router can ask "is there actually an
  application in this sentence?" *before* routing to automation.  Without
  it, "I've explained this three times and you're still not understanding
  me!" reached ``open_app`` and JARVIS answered as if an app were opening.
* the unconditional debug banner is now developer tracing
  (``config/settings.json -> pipeline_debug``).
* a failed launch returns a structured result instead of the bare string
  "FAILED", and no match returns ``None`` so the caller can ask the user
  what to open rather than claiming success.
"""

from core.normalizer import normalize
from brains_v2.trace import trace

from automation.window_manager import (
    is_window_open,
    focus_window,
)

import logging
import os
import re
import subprocess

log = logging.getLogger("jarvis.automation.apps")

APPS = {
    "notepad": ("notepad.exe", "Notepad"),
    "calculator": ("calc.exe", "Calculator"),
    "paint": ("mspaint.exe", "Paint"),
    "cmd": ("cmd.exe", "Command Prompt"),
    "explorer": ("explorer.exe", "File Explorer"),
    "chrome": (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "Google Chrome"
    ),
}

# Speech-recognition corrections.
REPLACEMENTS = {
    "not bad": "notepad",
    "note bad": "notepad",
    "node pad": "notepad",
    "not pet": "notepad",
    "not that": "notepad",
    "your bed": "notepad",
    "the bread": "notepad",
    "up the bread": "notepad",
    "no pad": "notepad",
    "note pad": "notepad",
    "chromee": "chrome",
    "google chrome": "chrome",
    "calculatore": "calculator",
    "calculatorulator": "calculator",
}

ALIASES = {
    "notepad": ("notepad",),
    "calculator": ("calculator", "calc"),
    "paint": ("paint", "mspaint"),
    "cmd": ("cmd", "command prompt", "terminal"),
    "explorer": ("explorer", "file explorer", "my computer"),
    "chrome": ("chrome", "google chrome", "browser"),
}


def prepare(command):
    """Normalised, speech-corrected form of ``command``."""

    text = normalize(command or "")

    for wrong, correct in REPLACEMENTS.items():
        text = text.replace(wrong, correct)

    return text.replace("calculatorulator", "calculator")


def match_app(command):
    """The application named in ``command``, or None.

    This is the guard the router uses: no application named means the
    sentence is not an automation request at all.
    """

    text = prepare(command)

    if not text:
        return None

    for app_name, names in ALIASES.items():
        for name in names:
            if re.search(rf"\b{re.escape(name)}\b", text):
                return app_name

    return None


def open_app(command):
    """Open the application named in ``command``.

    Returns ``None`` when no application was named - the caller must then
    ask the user instead of reporting success.
    """

    text = prepare(command)

    trace("APP -> normalized command:", text)

    app_name = match_app(command)

    if not app_name:
        trace("APP -> no application matched")
        log.info("no application named in %r", command)
        return None

    exe, window_title = APPS[app_name]

    trace("APP -> matched", app_name)

    # -------------------------
    # Already running?
    # -------------------------
    try:
        if is_window_open(window_title) and focus_window(window_title):
            trace("APP -> focused existing window")

            return {
                "status": "ALREADY_OPEN",
                "app": app_name,
            }

    except Exception as error:  # pragma: no cover - platform specific
        log.warning("window check failed for %s: %r", app_name, error)

    # -------------------------
    # Launch
    # -------------------------
    try:

        if app_name == "cmd":
            process = subprocess.Popen(
                ["cmd.exe"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            process = subprocess.Popen([exe])

        trace("APP -> pid", process.pid)

        return {
            "status": "OPENED",
            "app": app_name,
        }

    except Exception as error:

        log.warning("could not start %s: %r", app_name, error)

        return {
            "status": "FAILED",
            "app": app_name,
            "error": str(error),
        }


CLOSE_REQUEST = re.compile(
    r"\b(close|quit|exit|kill|terminate|shut\s*down)\b",
    re.IGNORECASE,
)


def is_close_request(command) -> bool:
    """True when the sentence asks for an application to be closed."""

    return bool(CLOSE_REQUEST.search(prepare(command) or ""))


def close_app(command):
    """Close the application named in ``command``.

    Returns ``None`` when no application was named, so the caller asks
    instead of guessing, and a structured status otherwise:

    * ``CLOSED``   - the process was asked to exit
    * ``NOT_OPEN`` - nothing was running under that name
    * ``FAILED``   - the attempt itself failed (reported honestly)
    """

    app_name = match_app(command)

    if not app_name:
        trace("APP -> close with no application matched")
        log.info("no application named in %r", command)

        return None

    exe = APPS[app_name][0]
    process_name = os.path.basename(exe).lower()

    try:
        import psutil

    except Exception as error:  # pragma: no cover - platform specific
        log.warning("psutil unavailable, cannot close %s: %r", app_name, error)

        return {
            "status": "FAILED",
            "app": app_name,
            "error": "psutil is not installed",
        }

    closed = 0

    for process in psutil.process_iter(["name"]):

        try:
            name = (process.info.get("name") or "").lower()

        except Exception:  # pragma: no cover - process vanished
            continue

        if name != process_name:
            continue

        try:
            process.terminate()
            closed += 1

        except Exception as error:
            log.warning("could not close %s: %r", app_name, error)

    trace("APP -> closed", app_name, closed)

    if not closed:
        return {
            "status": "NOT_OPEN",
            "app": app_name,
        }

    return {
        "status": "CLOSED",
        "app": app_name,
        "closed": closed,
    }


__all__ = [
    "APPS",
    "CLOSE_REQUEST",
    "match_app",
    "open_app",
    "close_app",
    "is_close_request",
    "prepare",
]
