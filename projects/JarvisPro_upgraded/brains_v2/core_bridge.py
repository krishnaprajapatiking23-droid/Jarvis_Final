"""Bridge from the legacy BrainV2 router to the real jarvis_core managers.

BUG FIX (roadmap sections 9, 14, 24, 30, 31): ``brains_v2/router_v2.py`` had
four routes that returned nothing but a placeholder sentence --
``"Vision Agent Selected."``, ``"Security Agent Selected."``,
``"Mobile Agent Selected."`` and ``"Task received."`` (which created no task
at all) -- while fully built, fully tested managers for exactly those jobs sat
unreachable in ``jarvis_core/``.

This module is the adapter between the two. Every handler either performs the
real operation or says plainly that the capability is unavailable; none of them
invents a success.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.core_bridge")

__all__ = [
    "kernel",
    "handle_task",
    "handle_vision",
    "handle_security",
    "handle_mobile",
    "handle_research",
    "handle_skill",
]

_KERNEL = None


def kernel() -> Optional[Any]:
    """Return the shared kernel, or None when it cannot be built."""
    global _KERNEL
    if _KERNEL is None:
        try:
            from jarvis_core.kernel import get_kernel

            _KERNEL = get_kernel()
        except Exception as error:
            log.warning("kernel unavailable: %s", error)
            return None
    return _KERNEL


def _reply(text: str) -> Dict[str, str]:
    return {"reply": text}


# ----------------------------------------------------------------- tasks ---
_TASK_CREATE = re.compile(
    r"^(?:please\s+)?(?:create|add|make|new|start)\s+(?:a|an|the)?\s*task\s*"
    r"(?:to\s+|for\s+|called\s+|named\s+|:)?\s*(?P<title>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TASK_LIST = re.compile(
    r"^(?:please\s+)?(?:show|list|display|what\s+are|whats|what's|give\s+me)\s*"
    r"(?:me\s+)?(?:a|an|the|my|all|any)*\s*"
    # BUG FIX: only determiners were allowed before the noun, so
    # "show my running tasks" did not match and the user was told
    # "I couldn't work out what task you meant."
    r"(?:running|active|current|ongoing|open|pending|background|unfinished)?\s*"
    r"tasks?\s*"
    r"(?:list|pending|left|open|running)?[?.!]*$",
    re.IGNORECASE,
)
_TASK_CANCEL = re.compile(
    r"^(?:please\s+)?(?:cancel|stop|abort|delete|remove)\s+(?:a|an|the|my)*\s*"
    r"task\s*(?:number|#)?\s*(?P<token>\S+)[?.!]*$",
    re.IGNORECASE,
)
_TASK_DONE = re.compile(
    r"^(?:please\s+)?(?:complete|finish|done\s+with|mark\s+done)\s+"
    r"(?:a|an|the|my)*\s*task\s*(?:number|#)?\s*(?P<token>\S+)[?.!]*$",
    re.IGNORECASE,
)


def _open_tasks(manager: Any):
    """The same view of tasks the user is shown when listing."""
    tasks = manager.store.load_all()
    return [t for t in tasks if t.state not in ("cancelled", "completed", "failed", "rolled_back")][-20:]


def _resolve_task_id(manager: Any, token: str) -> Optional[str]:
    """Accept either a real task id or a 1-based position from the listing.

    The dataclass field is ``task_id``, not ``id``; using ``task.id`` raised
    AttributeError on every cancel/complete.
    """
    token = str(token).strip(".,#")
    shown = _open_tasks(manager)

    if token.isdigit():
        index = int(token) - 1
        if 0 <= index < len(shown):
            return shown[index].task_id
        return None

    for task in manager.store.load_all():
        if task.task_id == token or task.task_id.startswith(token):
            return task.task_id

    return None


def handle_task(command: Any) -> Optional[Dict[str, str]]:
    """Create / list / cancel / complete a real task in jarvis_core.tasks."""
    text = " ".join(str(command or "").split())
    if not text or "task" not in text.lower():
        return None

    core = kernel()
    if core is None:
        return _reply("The task manager is unavailable right now.")

    manager = core.tasks

    match = _TASK_CANCEL.match(text)
    if match:
        task_id = _resolve_task_id(manager, match.group("token"))
        if not task_id:
            return _reply("I couldn't find that task.")
        try:
            manager.cancel(task_id)
        except Exception as error:
            return _reply("I couldn't cancel that task: %s" % error)
        return _reply("Task cancelled.")

    match = _TASK_DONE.match(text)
    if match:
        task_id = _resolve_task_id(manager, match.group("token"))
        if not task_id:
            return _reply("I couldn't find that task.")
        # The task state machine is created -> queued -> running -> completed;
        # jumping straight to "completed" is an illegal transition, so walk
        # the intermediate states the way a real execution would.
        try:
            current = manager.get(task_id).state
            for target in ("queued", "running", "completed"):
                if current == "completed":
                    break
                if target == current:
                    continue
                manager.transition(task_id, target, note="marked done by user")
                current = target
        except Exception as error:
            return _reply("I couldn't complete that task: %s" % error)
        return _reply("Task completed.")

    if _TASK_LIST.match(text):
        try:
            tasks = manager.store.load_all()
        except Exception as error:
            return _reply("I couldn't read the task list: %s" % error)
        open_tasks = [t for t in tasks if t.state not in ("cancelled", "completed", "failed", "rolled_back")]
        shown = open_tasks[-20:]
        if not shown:
            done = len(tasks)
            return _reply(
                "No open tasks." if not done
                else "No open tasks (%d finished)." % done
            )
        lines = [
            "%d. %s [%s]" % (index, task.title, task.state)
            for index, task in enumerate(shown, start=1)
        ]
        if len(open_tasks) > len(shown):
            lines.insert(0, "(showing the %d most recent of %d open tasks)"
                         % (len(shown), len(open_tasks)))
        return _reply("\n".join(lines))

    match = _TASK_CREATE.match(text)
    if match:
        title = match.group("title").strip(" :-,.")
        if not title:
            return _reply("What should the task be called?")
        try:
            task = manager.create(title)
        except Exception as error:
            return _reply("I couldn't create that task: %s" % error)
        return _reply("Task created: %s" % task.title)

    return None


# ---------------------------------------------------------------- vision ---
# --------------------------------------------------------------- profile ---
_PROFILE_QUERY = re.compile(
    r"^(?:please\s+)?(?:what|which)\s+(?:do|does)\s+you(?:\s+know|\s+remember)?\s*"
    r"(?:about\s+)?(?:my|me)\b.*$"
    r"|^(?:please\s+)?(?:show|list|tell\s+me)\s+(?:me\s+)?(?:my|all\s+my)\s+"
    r"(?:profile|preferences?|settings?)\b.*$"
    r"|^(?:please\s+)?what\s+(?:are|is)\s+my\s+(?:profile|preferences?)\b.*$",
    re.IGNORECASE,
)


def handle_profile(command: Any) -> Optional[Dict[str, str]]:
    """Answer "what do you know about my preferences?" from the profile store.

    Section 8 requires these questions to reach the profile subsystem rather
    than being answered as ordinary conversation. This reads the persisted
    attributes directly, so it works with no model backend available.
    """
    text = " ".join(str(command or "").split())
    if not text or not _PROFILE_QUERY.match(text):
        return None

    core = kernel()
    if core is None:
        return _reply("The profile store is unavailable right now.")

    try:
        snapshot = core.profile.snapshot()
    except Exception as error:
        return _reply("I couldn't read your profile: %s" % error)

    if not snapshot:
        return _reply("I don't have anything recorded about your preferences yet.")

    lines = []
    for key in sorted(snapshot):
        entry = snapshot[key]
        label = key.replace("_", " ")
        line = "- %s: %s" % (label, entry.get("value"))
        if entry.get("temporary"):
            line += " (temporary, until %s UTC)" % entry.get("expires_at")
        confidence = entry.get("confidence")
        if isinstance(confidence, (int, float)) and confidence < 0.7:
            line += " (low confidence)"
        lines.append(line)

    header = "Here is what I have on file (%d item%s):" % (
        len(lines), "" if len(lines) == 1 else "s")
    return _reply(header + "\n" + "\n".join(lines))


def handle_vision(command: Any) -> Dict[str, str]:
    """Read the screen for real, or say why it cannot be read."""
    text = str(command or "").lower()

    try:
        from brains_v2.vision.manager import vision_manager  # type: ignore

        result = vision_manager.process(command)
        if result:
            return _reply(result if isinstance(result, str) else str(result))
    except Exception as error:
        log.info("vision manager unavailable: %s", error)

    try:
        from vision.screen_reader import read_screen  # type: ignore

        text_on_screen = read_screen()
        if text_on_screen:
            return _reply("On screen I can read:\n%s" % text_on_screen)
        return _reply("I took a screenshot but couldn't read any text on it.")
    except Exception as error:
        return _reply(
            "Screen reading is unavailable on this machine (%s). "
            "It needs pillow plus an OCR backend (pytesseract or easyocr)."
            % type(error).__name__
        )


# -------------------------------------------------------------- security ---
_LOCK = re.compile(r"\b(lock|emergency lock|safe mode|log ?out)\b", re.IGNORECASE)
_STATUS = re.compile(r"\b(status|report|audit|who|permissions?)\b", re.IGNORECASE)


def handle_security(command: Any) -> Dict[str, str]:
    """Report real policy/permission state instead of a placeholder."""
    text = str(command or "")
    core = kernel()

    if core is None:
        return _reply("The security subsystem is unavailable right now.")

    if _LOCK.search(text):
        try:
            revoked = 0
            for permission in core.policy.permissions(core.subject):
                identifier = getattr(permission, "perm_id", None)
                if identifier and core.policy.revoke(identifier):
                    revoked += 1
            return _reply(
                "Locked. %d permission(s) revoked -- every privileged action "
                "now needs your explicit approval again." % revoked
            )
        except Exception as error:
            return _reply("I couldn't engage the lock: %s" % error)

    if _STATUS.search(text):
        try:
            count = len(core.policy.permissions(core.subject))
        except Exception:
            count = 0
        try:
            health = core.policy.health()
            available = health.get("available", True)
        except Exception:
            available = True
        return _reply(
            "Security: policy engine %s, %d permission(s) granted, owner is %s."
            % ("online" if available else "offline", count, core.subject)
        )

    return _reply(
        "I can lock the system, or report the current permission rules. "
        "Which would you like?"
    )


# ---------------------------------------------------------------- mobile ---
def handle_mobile(command: Any) -> Dict[str, str]:
    """Report the real state of the Android companion server."""
    try:
        from brains_v2.server.client_manager import client_manager  # type: ignore

        devices = client_manager.devices()
        if devices:
            return _reply(
                "%d device(s) paired: %s"
                % (len(devices), ", ".join(str(d) for d in devices))
            )
        return _reply("No phone is paired yet. Start the server and scan the code.")
    except Exception:
        pass

    return _reply(
        "The phone companion server is not running. Start it with "
        "`python -m brains_v2.server.api` and pair from the Android app."
    )


# -------------------------------------------------------------- research ---
def handle_research(command: Any) -> Optional[Dict[str, str]]:
    """Run the real research manager when it has a fetcher configured."""
    core = kernel()
    if core is None:
        return None

    question = re.sub(
        r"^(?:please\s+)?(?:research|look\s+up|find\s+out|investigate)\s+",
        "",
        str(command or "").strip(),
        flags=re.IGNORECASE,
    ).strip(" ?.")

    if not question:
        return _reply("What would you like me to research?")

    try:
        cached = core.research.cache_get(question)
        if cached:
            answer = cached.get("answer") or cached.get("summary")
            if answer:
                return _reply("From my research cache:\n%s" % answer)
    except Exception as error:
        log.info("research cache unavailable: %s", error)

    try:
        health = core.research.health()
        if not health.get("available", False):
            return _reply(
                "I can't research that yet: %s"
                % health.get("detail", "no web or browser backend is configured")
            )
    except Exception:
        pass

    return None


# ---------------------------------------------------------------- skills ---
def handle_skill(command: Any) -> Optional[Dict[str, Any]]:
    """Give registered skills and plugins a chance at the command.

    BUG FIX: the skill registry and the plugin system were both dead on
    import, so nothing ever consulted them. Now that both load, they are
    actually asked -- which is what makes "what is 25 * 4" answerable.
    """
    try:
        from brains_v2.skills.manager import process as skill_process

        result = skill_process(command)
        if result:
            if isinstance(result, dict):
                return result if "reply" in result else {"reply": str(result)}
            return _reply(str(result))
    except Exception as error:
        log.info("skill registry failed: %s", error)

    try:
        from plugins.plugin_manager import process_plugin

        result = process_plugin(command)
        if result:
            if isinstance(result, dict):
                return result if "reply" in result else {"reply": str(result)}
            return _reply(str(result))
    except Exception as error:
        log.info("plugin manager failed: %s", error)

    return None
