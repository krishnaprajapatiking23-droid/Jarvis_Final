"""Telegram bot integration for Jarvis.

Implements real Telegram Bot API using python-telegram-bot.
Configuration is token-based via config/telegram.json or TELEGRAM_BOT_TOKEN env var.

Permissions required by the bot (set via BotFather /privacy):
  - read messages in private chats and groups where the bot is added
  - send messages, photos, documents

Security:
  - All incoming messages go through the normal Jarvis command pipeline.
  - Owner-only commands are gated by the security subsystem.
  - No token or API secret is ever logged or exposed.

Usage:
  1. Create a bot via @BotFather → copy the HTTP API token.
  2. Save it as config/telegram.json:
     {"bot_token": "YOUR_TOKEN_HERE", "owner_chat_id": "YOUR_CHAT_ID"}
     OR set the TELEGRAM_BOT_TOKEN environment variable.
  3. Start Jarvis. The bot connects automatically.
  4. Send /start to the bot to register your chat ID.

Commands:
  /start       — Register your chat ID as the owner
  /status      — Show Jarvis system status
  /screenshot  — Take and send a screenshot
  /memory      — Show recent memory entries
  /help        — Show available commands
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

__all__ = ["TelegramBot", "get_telegram_bot"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    """Load Telegram config from file or environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
    if not token:
        config_path = "config/telegram.json"
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    data = json.load(f)
                token = data.get("bot_token", "") or data.get("token", "")
                owner_chat_id = owner_chat_id or str(data.get("owner_chat_id", ""))
            except Exception as exc:
                log.warning("Failed to load %s: %s", config_path, exc)
    return {"bot_token": token, "owner_chat_id": owner_chat_id}


@dataclass
class TelegramConfig:
    bot_token: str
    owner_chat_id: str
    owner_only: bool = True  # Only respond to the owner's chat ID
    admin_ids: List[str] = None  # Additional allowed user IDs
    allowed_groups: List[str] = None  # Allowed group IDs
    block_groups: bool = True  # Reject all group messages

    def __post_init__(self) -> None:
        if self.admin_ids is None:
            self.admin_ids = []
        if self.allowed_groups is None:
            self.allowed_groups = []

    def is_authorized(self, chat_id: str) -> bool:
        if not self.owner_only:
            return True
        return str(chat_id) == str(self.owner_chat_id) or str(chat_id) in self.admin_ids

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelegramConfig":
        return cls(
            bot_token=data.get("bot_token", "") or data.get("token", ""),
            owner_chat_id=str(data.get("owner_chat_id", "")),
            owner_only=data.get("owner_only", True),
            admin_ids=[str(x) for x in data.get("admin_ids", [])],
            allowed_groups=[str(x) for x in data.get("allowed_groups", [])],
            block_groups=data.get("block_groups", True),
        )


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

@dataclass
class TelegramMessage:
    update_id: int
    chat_id: str
    text: str
    sender_id: str
    sender_name: str
    is_group: bool
    raw: Dict[str, Any]

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")


class TelegramBot:
    """Telegram bot that bridges messages to the Jarvis command pipeline.

    Thread-safety: all public methods are thread-safe. The polling loop runs
    in a daemon thread. Call ``shutdown()`` to cleanly stop it.
    """

    def __init__(
        self,
        config: Optional[TelegramConfig] = None,
        command_handler: Optional[Callable[[str], str]] = None,
    ) -> None:
        """
        Args:
            config: Telegram configuration. Loaded from file/env if omitted.
            command_handler: Callback that receives text and returns a response
                            string. Defaults to JarvisRuntime.process().
        """
        if config is None:
            raw = _load_config()
            config = TelegramConfig(
                bot_token=raw.get("bot_token", ""),
                owner_chat_id=raw.get("owner_chat_id", ""),
            )
        self._config = config
        self._command_handler = command_handler
        self._token = config.bot_token
        self._running = False
        self._lock = threading.RLock()
        self._poll_thread: Optional[threading.Thread] = None
        self._offset = 0  # Telegram update offset for polling
        self._message_count = 0
        self._connected = False
        self._start_time = 0.0
        self._owner_registered = bool(config.owner_chat_id)

        # Rate limiting (simple token bucket per chat)
        self._rate_limits: Dict[str, List[float]] = {}
        self._rate_limit_lock = threading.Lock()
        self._RATE_LIMIT = 5  # messages per 10 seconds per chat

        # Pending confirmations for high-risk commands
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self._confirmation_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    # ------------------------------------------------------------------
    # Telegram API (raw HTTP — no external library dependency)
    # ------------------------------------------------------------------

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _post(self, method: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a POST request to the Telegram Bot API."""
        import urllib.request
        import urllib.parse

        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            self._api_url(method),
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result.get('description', 'unknown')}")
        return result

    def _get_me(self) -> Dict[str, Any]:
        """Verify the bot token and get bot info."""
        return self._post("getMe")

    def _send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown",
                      reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a text message."""
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self._post("sendMessage", data)

    def _send_photo(self, chat_id: str, photo_data: bytes, caption: str = "",
                    filename: str = "screenshot.png") -> Dict[str, Any]:
        """Send a photo."""
        import urllib.request
        import urllib.parse

        boundary = "----TelegramBoundary----"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + photo_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            self._api_url("sendPhoto"),
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result.get('description', 'unknown')}")
        return result

    def _get_updates(self, offset: int = 0, timeout: int = 30) -> List[Dict[str, Any]]:
        """Get new updates from Telegram."""
        import urllib.request

        url = f"{self._api_url('getUpdates')}?offset={offset}&timeout={timeout}&allowed_updates=message"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            return []
        return result.get("result", [])

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------

    def _parse_message(self, update: Dict[str, Any]) -> Optional[TelegramMessage]:
        try:
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            from_user = msg.get("from", {})

            # Extract text
            text = msg.get("text", "") or msg.get("caption", "") or ""
            if not text:
                return None

            chat_id = str(chat.get("id", ""))
            sender_id = str(from_user.get("id", ""))
            sender_name = from_user.get("first_name", "Unknown")
            if from_user.get("last_name"):
                sender_name += " " + from_user.get("last_name")

            # Determine if group
            chat_type = chat.get("type", "private")
            is_group = chat_type != "private"

            return TelegramMessage(
                update_id=update.get("update_id", 0),
                chat_id=chat_id,
                text=text.strip(),
                sender_id=sender_id,
                sender_name=sender_name,
                is_group=is_group,
                raw=update,
            )
        except Exception as exc:
            log.warning("Failed to parse Telegram update: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _check_rate_limit(self, chat_id: str) -> bool:
        """Return True if the message is within rate limits."""
        now = time.time()
        with self._rate_limit_lock:
            if chat_id not in self._rate_limits:
                self._rate_limits[chat_id] = []
            # Remove messages older than 10 seconds
            self._rate_limits[chat_id] = [
                t for t in self._rate_limits[chat_id] if now - t < 10.0
            ]
            if len(self._rate_limits[chat_id]) >= self._RATE_LIMIT:
                return False
            self._rate_limits[chat_id].append(now)
            return True

    # ------------------------------------------------------------------
    # Security & authorization
    # ------------------------------------------------------------------

    def _is_authorized(self, msg: TelegramMessage) -> bool:
        if msg.is_group and self._config.block_groups:
            return False
        if self._config.allowed_groups and msg.is_group:
            return msg.chat_id in self._config.allowed_groups
        return self._config.is_authorized(msg.sender_id)

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    def _handle_command(self, msg: TelegramMessage) -> Optional[str]:
        """Handle Telegram-specific /commands. Returns None to pass to brain."""
        cmd = msg.text.split()[0].lower()

        if cmd == "/start":
            # Register owner
            if not self._owner_registered:
                self._config.owner_chat_id = msg.chat_id
                self._owner_registered = True
                self._save_config()
                return (
                    "✅ *Jarvis registered!*\n\n"
                    "Your chat ID has been set as the owner.\n"
                    "You can now control Jarvis via Telegram.\n\n"
                    "Send a message and I'll relay it to Jarvis.\n"
                    "Type /help for all commands."
                )
            return "👋 Jarvis is already configured!"

        if cmd == "/status":
            return self._get_status_text()

        if cmd == "/help":
            return self._get_help_text()

        if cmd == "/screenshot":
            if not self._is_authorized(msg):
                return "⛔ Unauthorized."
            return self._handle_screenshot(msg)

        if cmd == "/memory":
            if not self._is_authorized(msg):
                return "⛔ Unauthorized."
            return self._handle_memory(msg)

        if cmd == "/confirm":
            return self._handle_confirmation(msg)

        # Unknown command → pass to brain
        return None

    def _get_status_text(self) -> str:
        from jarvis_core.capability_registry import get_capability_registry
        reg = get_capability_registry()
        reg.refresh(force=True)
        summary = reg.summary()
        jstatus = reg.jarvis_status()
        lines = [
            "📊 *Jarvis Status*",
            f"Runtime: {jstatus.get('runtime', 'UNKNOWN')}",
            f"Overall: `{jstatus.get('overall', 'UNKNOWN')}`",
            "",
            f"Available: {summary.get('available', 0)}",
            f"Degraded: {summary.get('degraded', 0)}",
            f"Not Configured: {summary.get('not_configured', 0)}",
            f"Unavailable: {summary.get('unavailable', 0)}",
            "",
            f"Messages received: {self._message_count}",
            f"Uptime: {int(self.uptime)}s",
        ]
        return "\n".join(lines)

    def _get_help_text(self) -> str:
        return (
            "*Jarvis Telegram Commands*\n\n"
            "/start — Register as owner\n"
            "/status — System status\n"
            "/screenshot — Take screenshot\n"
            "/memory — Recent memories\n"
            "/help — This message\n\n"
            "Any other message is sent directly to Jarvis."
        )

    def _handle_screenshot(self, msg: TelegramMessage) -> str:
        try:
            import mss
            import numpy as np
            import cv2

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
            arr = np.array(img)
            rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            _, png = cv2.imencode(".png", rgb)
            self._send_photo(msg.chat_id, png.tobytes(), " Jarvis Screenshot")
            return "📸 Screenshot sent."
        except Exception as exc:
            return f"❌ Screenshot failed: {exc}"

    def _handle_memory(self, msg: TelegramMessage) -> str:
        try:
            from memory.manager import MemoryManager

            mgmt = MemoryManager()
            entries = mgmt.search("", limit=5)
            if not entries:
                return "📭 No memory entries found."
            lines = ["🧠 *Recent Memories*", ""]
            for e in entries[:5]:
                content = (e.get("content", str(e))[:80])
                lines.append(f"• {content}")
            return "\n".join(lines)
        except Exception as exc:
            return f"❌ Memory error: {exc}"

    def _handle_confirmation(self, msg: TelegramMessage) -> str:
        key = f"{msg.chat_id}:{msg.sender_id}"
        with self._confirmation_lock:
            if key in self._pending_confirmations:
                confirm_data = self._pending_confirmations.pop(key)
                action = confirm_data.get("action", "execute")
                try:
                    result = confirm_data["callback"]()
                    return f"✅ Confirmed: {action} — {result}"
                except Exception as exc:
                    return f"❌ Execution failed: {exc}"
        return "No pending confirmation found."

    def _request_confirmation(
        self, chat_id: str, sender_id: str, action: str, callback: Callable[[], str]
    ) -> None:
        key = f"{chat_id}:{sender_id}"
        with self._confirmation_lock:
            self._pending_confirmations[key] = {"action": action, "callback": callback}
        self._send_message(
            chat_id,
            f"⚠️ Confirm: {action}?\nReply with /confirm to proceed.",
        )

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, msg: TelegramMessage) -> None:
        """Process one incoming message."""
        self._message_count += 1
        log.info(
            "[Telegram] %s (%s): %s",
            msg.sender_name,
            msg.sender_id,
            msg.text[:80],
        )

        # Rate limit check
        if not self._check_rate_limit(msg.chat_id):
            self._send_message(msg.chat_id, "⏳ Too many requests. Please wait.")
            return

        # Authorization check
        if not self._is_authorized(msg):
            log.warning(
                "[Telegram] Unauthorized access from %s (%s)",
                msg.sender_name,
                msg.sender_id,
            )
            self._send_message(
                msg.chat_id,
                "⛔ You are not authorized to use this bot.",
            )
            return

        # Built-in command?
        if msg.is_command:
            result = self._handle_command(msg)
            if result is not None:
                self._send_message(msg.chat_id, result)
                return

        # Pass to brain
        text = msg.text
        handler = self._command_handler
        if handler is None:
            from brains_v2.runtime import get_runtime

            def default_handler(t: str) -> str:
                runtime = get_runtime()
                reply = runtime.process(t)
                # Extract canonical reply
                if hasattr(reply, "reply_text"):
                    return str(reply.reply_text)
                if isinstance(reply, dict):
                    return str(reply.get("reply_text", reply.get("text", str(reply))))
                return str(reply) if reply else "No response."

            handler = default_handler

        try:
            response = handler(text)
            self._send_message(msg.chat_id, str(response))
        except Exception as exc:
            log.error("[Telegram] Brain error: %s", exc)
            self._send_message(msg.chat_id, f"❌ Error: {exc}")

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        log.info("[Telegram] Polling thread started (offset=%d)", self._offset)
        consecutive_errors = 0
        while self._running:
            try:
                updates = self._get_updates(offset=self._offset, timeout=5)
                for update in updates:
                    update_id = update.get("update_id", 0)
                    msg = self._parse_message(update)
                    if msg is not None:
                        self._dispatch(msg)
                    # Advance offset
                    if update_id >= self._offset:
                        self._offset = update_id + 1
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                wait = min(30, 2**consecutive_errors)
                log.warning(
                    "[Telegram] Poll error (consecutive=%d, wait=%ds): %s",
                    consecutive_errors,
                    wait,
                    exc,
                )
                time.sleep(wait)

        log.info("[Telegram] Polling thread stopped")

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Verify token and start the polling thread. Returns True on success."""
        if not self.is_configured:
            log.error("[Telegram] Not configured: no bot token found.")
            return False

        try:
            me = self._get_me()
            bot_name = me.get("result", {}).get("first_name", "Unknown")
            log.info("[Telegram] Bot verified: @%s", bot_name)
        except Exception as exc:
            log.error("[Telegram] Token verification failed: %s", exc)
            return False

        with self._lock:
            if self._running:
                log.warning("[Telegram] Already connected")
                return True
            self._running = True
            self._start_time = time.time()
            self._poll_thread = threading.Thread(target=self._poll, daemon=True)
            self._poll_thread.start()
            self._connected = True
            log.info("[Telegram] Connected and polling")
            return True

    def disconnect(self) -> None:
        """Stop polling cleanly."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._connected = False
        log.info("[Telegram] Disconnecting...")

    def shutdown(self) -> None:
        self.disconnect()
        self._poll_thread = None

    # ------------------------------------------------------------------
    # Outbound helpers (for other modules to send via Telegram)
    # ------------------------------------------------------------------

    def notify_owner(self, message: str) -> bool:
        """Send a notification to the registered owner. Returns True on success."""
        owner_id = self._config.owner_chat_id
        if not owner_id:
            log.warning("[Telegram] No owner chat ID configured")
            return False
        try:
            self._send_message(owner_id, message)
            return True
        except Exception as exc:
            log.error("[Telegram] Failed to notify owner: %s", exc)
            return False

    def send_screenshot_to_owner(self, caption: str = "") -> bool:
        """Capture and send screenshot to owner. Returns True on success."""
        owner_id = self._config.owner_chat_id
        if not owner_id:
            return False
        try:
            import mss
            import numpy as np
            import cv2

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
            arr = np.array(img)
            rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            _, png = cv2.imencode(".png", rgb)
            self._send_photo(owner_id, png.tobytes(), caption)
            return True
        except Exception as exc:
            log.error("[Telegram] Screenshot to owner failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        os.makedirs("config", exist_ok=True)
        config_path = "config/telegram.json"
        try:
            with open(config_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing["owner_chat_id"] = self._config.owner_chat_id
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)
        log.info("[Telegram] Config saved: owner_chat_id=%s", self._config.owner_chat_id)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured,
            "connected": self._connected,
            "owner_registered": self._owner_registered,
            "owner_chat_id": self._config.owner_chat_id,
            "message_count": self._message_count,
            "uptime_seconds": round(self.uptime, 1),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_TELEGRAM_BOT: Optional[TelegramBot] = None
_TELEGRAM_LOCK = threading.Lock()


def get_telegram_bot() -> TelegramBot:
    global _TELEGRAM_BOT
    with _TELEGRAM_LOCK:
        if _TELEGRAM_BOT is None:
            _TELEGRAM_BOT = TelegramBot()
        return _TELEGRAM_BOT


def connect_telegram(command_handler: Optional[Callable[[str], str]] = None) -> bool:
    """Convenience: get and connect the Telegram bot."""
    bot = get_telegram_bot()
    if command_handler:
        bot._command_handler = command_handler
    return bot.connect()
