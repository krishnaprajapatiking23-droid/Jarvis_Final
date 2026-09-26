"""WhatsApp delivery with a validated automation ladder (BUG 6).

Level 1 - Meta/WhatsApp Cloud API when credentials are configured.
Level 2 - desktop automation that *locates* its target: window discovery,
          activation, visibility check and image-anchor matching.
Level 3 - window-relative coordinate fallback, only when explicitly allowed
          and only after the window has been found, activated and verified.

Nothing ever clicks blindly. If the target cannot be located the attempt is
aborted with :data:`TARGET_NOT_FOUND`. Coordinates are fractions of the
found window rectangle, so window moves/resizes, multi-monitor layouts and
DPI scaling do not send text to the wrong element.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from integrations.base import IntegrationResult
except Exception:  # pragma: no cover - base is always present in-tree
    @dataclass
    class IntegrationResult:  # type: ignore[no-redef]
        ok: bool
        data: Any = None
        error: str = ""
        environment_ready: bool = False

__all__ = [
    "TARGET_NOT_FOUND",
    "ANCHOR_DIRECTORY",
    "WINDOW_TITLE_HINTS",
    "CloudAPI",
    "WindowTarget",
    "DesktopAutomation",
    "UIAutomationFallback",
    "WhatsApp",
    "whatsapp",
]

log = logging.getLogger(__name__)

TARGET_NOT_FOUND = "Automation failed: WhatsApp target could not be located."
ANCHOR_DIRECTORY = os.environ.get("JARVIS_WHATSAPP_ANCHORS", "assets/whatsapp")
WINDOW_TITLE_HINTS: Tuple[str, ...] = ("whatsapp",)


class CloudAPI:
    """Level 1: the official Cloud API."""

    BASE_URL = "https://graph.facebook.com/v20.0"

    def __init__(self, token: str = "", phone_id: str = "") -> None:
        self.token = token or os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_id = phone_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.phone_id)

    def send(self, to: str, text: str) -> IntegrationResult:
        """Send a text message through the Cloud API."""
        if not self.configured:
            return IntegrationResult(
                ok=False,
                error=(
                    "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are "
                    "required for the WhatsApp Cloud API"
                ),
            )
        if not to or not text:
            return IntegrationResult(ok=False, error="recipient and text are required")

        url = "%s/%s/messages" % (self.BASE_URL, self.phone_id)
        payload = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": str(to),
                "type": "text",
                "text": {"body": str(text)},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": "Bearer %s" % self.token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except Exception as error:
            return IntegrationResult(
                ok=False,
                error="WhatsApp Cloud API request failed: %r" % error,
                environment_ready=True,
            )
        return IntegrationResult(ok=True, data=body, environment_ready=True)


@dataclass
class WindowTarget:
    """A located, on-screen WhatsApp window (absolute desktop coordinates)."""

    title: str
    left: int
    top: int
    width: int
    height: int
    handle: Any = None

    @property
    def visible(self) -> bool:
        return self.width > 200 and self.height > 200

    def point(self, x_fraction: float, y_fraction: float) -> Tuple[int, int]:
        """Window-relative fraction -> absolute screen point."""
        x = int(self.left + self.width * float(x_fraction))
        y = int(self.top + self.height * float(y_fraction))
        return x, y


class DesktopAutomation:
    """Levels 2 and 3: located desktop automation with a safe abort."""

    # Window-relative fractions, never absolute screen pixels.
    SEARCH_BOX = (0.18, 0.12)
    MESSAGE_BOX = (0.60, 0.94)

    def __init__(
        self,
        dry_run: bool = False,
        allow_coordinate_fallback: bool = False,
        anchor_directory: Any = ANCHOR_DIRECTORY,
    ) -> None:
        self.dry_run = bool(dry_run)
        self.allow_coordinate_fallback = bool(allow_coordinate_fallback)
        self.anchor_directory = Path(anchor_directory)
        self.steps: List[str] = []

    # ------------------------------------------------------------ discovery
    def find_window(self) -> Optional[WindowTarget]:
        """Locate a WhatsApp window through pygetwindow, if available."""
        self.steps.append("find_window")
        try:
            import pygetwindow
        except Exception as error:
            log.info("window discovery unavailable: %r", error)
            return None
        try:
            windows = pygetwindow.getAllWindows()
        except Exception as error:
            log.info("window enumeration failed: %r", error)
            return None
        for window in windows or []:
            title = str(getattr(window, "title", "") or "")
            if not any(hint in title.lower() for hint in WINDOW_TITLE_HINTS):
                continue
            try:
                target = WindowTarget(
                    title=title,
                    left=int(window.left),
                    top=int(window.top),
                    width=int(window.width),
                    height=int(window.height),
                    handle=window,
                )
            except Exception:
                continue
            if target.visible:
                return target
        return None

    def activate(self, target: WindowTarget) -> bool:
        """Restore and focus the window before interacting with it."""
        self.steps.append("activate")
        handle = target.handle
        if handle is None:
            return False
        try:
            if getattr(handle, "isMinimized", False):
                handle.restore()
            handle.activate()
        except Exception as error:
            log.info("window activation failed: %r", error)
            return False
        return True

    def locate_anchor(self, name: str) -> Optional[Tuple[int, int]]:
        """Template-match a UI anchor image and return its centre."""
        self.steps.append("locate_anchor:%s" % name)
        image = self.anchor_directory / ("%s.png" % name)
        if not image.is_file():
            return None
        try:
            import pyautogui
        except Exception as error:
            log.info("pyautogui unavailable: %r", error)
            return None
        try:
            box = pyautogui.locateOnScreen(str(image), confidence=0.85)
        except TypeError:
            try:
                box = pyautogui.locateOnScreen(str(image))
            except Exception as error:
                log.info("anchor match failed: %r", error)
                return None
        except Exception as error:
            log.info("anchor match failed: %r", error)
            return None
        if box is None:
            return None
        centre = pyautogui.center(box)
        return int(centre[0]), int(centre[1])

    # -------------------------------------------------------------- sending
    def _abort(self, reason: str) -> IntegrationResult:
        log.warning("whatsapp automation aborted: %s", reason)
        return IntegrationResult(
            ok=False, error=TARGET_NOT_FOUND, data={"reason": reason, "steps": self.steps}
        )

    def send(self, contact: str, text: str) -> IntegrationResult:
        """Type a message into the located WhatsApp window."""
        self.steps = []
        if not contact or not text:
            return IntegrationResult(ok=False, error="contact and text are required")

        target = self.find_window()
        if target is None:
            return self._abort("WhatsApp window not found")
        if not target.visible:
            return self._abort("WhatsApp window is not visible")
        if not self.activate(target) and not self.dry_run:
            return self._abort("WhatsApp window could not be activated")

        search_point = self.locate_anchor("search_box")
        message_point = self.locate_anchor("message_box")
        strategy = "anchor"

        if search_point is None or message_point is None:
            if not self.allow_coordinate_fallback:
                return self._abort("UI anchors not found and fallback disabled")
            strategy = "window-relative"
            search_point = target.point(*self.SEARCH_BOX)
            message_point = target.point(*self.MESSAGE_BOX)
            if not self._inside(target, search_point) or not self._inside(
                target, message_point
            ):
                return self._abort("computed points fall outside the window")

        if self.dry_run:
            self.steps.append("dry-run")
            return IntegrationResult(
                ok=False,
                error=TARGET_NOT_FOUND,
                data={
                    "reason": "dry run: no input was sent",
                    "strategy": strategy,
                    "steps": self.steps,
                },
            )

        try:
            import pyautogui
        except Exception as error:
            return self._abort("pyautogui unavailable: %r" % error)

        try:
            pyautogui.click(*search_point)
            pyautogui.typewrite(str(contact), interval=0.02)
            pyautogui.press("enter")
            pyautogui.click(*message_point)
            pyautogui.typewrite(str(text), interval=0.02)
            pyautogui.press("enter")
        except Exception as error:
            return self._abort("input failed: %r" % error)

        self.steps.append("sent")
        return IntegrationResult(
            ok=True,
            data={"strategy": strategy, "window": target.title, "steps": self.steps},
            environment_ready=True,
        )

    @staticmethod
    def _inside(target: WindowTarget, point: Tuple[int, int]) -> bool:
        x, y = point
        return (
            target.left <= x <= target.left + target.width
            and target.top <= y <= target.top + target.height
        )


class UIAutomationFallback(DesktopAutomation):
    """Explicit alias for the coordinate-enabled variant."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("allow_coordinate_fallback", True)
        super().__init__(**kwargs)


@dataclass
class WhatsApp:
    """Public WhatsApp entry point used by the tool registry."""

    cloud: CloudAPI = field(default_factory=CloudAPI)
    desktop: Optional[DesktopAutomation] = None

    def __post_init__(self) -> None:
        if self.desktop is None:
            allow_desktop = os.environ.get(
                "JARVIS_WHATSAPP_ALLOW_DESKTOP", ""
            ).strip().lower() in ("1", "true", "yes")
            self.desktop = DesktopAutomation(
                allow_coordinate_fallback=allow_desktop
            ) if allow_desktop else None

    @property
    def strategy(self) -> str:
        if self.cloud.configured:
            return "cloud-api"
        if self.desktop is not None:
            return "desktop"
        return "unconfigured"

    def status(self) -> Dict[str, Any]:
        """Honest report of what WhatsApp delivery can do right now."""
        return {
            "strategy": self.strategy,
            "cloud_api_configured": self.cloud.configured,
            "desktop_enabled": self.desktop is not None,
        }

    def send(self, to: str, text: str) -> IntegrationResult:
        """Send through the highest available level; never click blindly."""
        if self.cloud.configured:
            return self.cloud.send(to, text)
        if self.desktop is not None:
            return self.desktop.send(to, text)
        return IntegrationResult(
            ok=False,
            error=(
                "WhatsApp is not configured: set WHATSAPP_ACCESS_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID, or enable desktop automation with "
                "JARVIS_WHATSAPP_ALLOW_DESKTOP=1"
            ),
        )

    @staticmethod
    def web_link(to: str, text: str = "") -> str:
        """Build a wa.me link the user can open manually."""
        digits = "".join(character for character in str(to) if character.isdigit())
        query = urllib.parse.urlencode({"text": str(text)}) if text else ""
        return "https://wa.me/%s?%s" % (digits, query) if query else "https://wa.me/%s" % digits


whatsapp = WhatsApp()
