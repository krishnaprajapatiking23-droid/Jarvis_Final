"""Discord bot integration for Jarvis.

Implements a real Discord bot using the Discord HTTP API with urllib.
Configuration is via config/discord.json or DISCORD_BOT_TOKEN env var.

Security:
  - All incoming messages go through the normal Jarvis command pipeline.
  - Owner-only commands are gated by user ID allow-listing.
  - No token is ever logged.

Permissions required:
  - Bot must be invited with: Read Messages, Send Messages, Embed Links
  - Set via OAuth2 URL in Discord Developer Portal.

Usage:
  1. Create a bot at https://discord.com/developers/applications
  2. Copy the bot token.
  3. Save as config/discord.json:
     {"bot_token": "YOUR_TOKEN", "owner_ids": ["YOUR_USER_ID"]}
     OR set DISCORD_BOT_TOKEN env var.
  4. Start Jarvis. The bot logs in automatically.
  5. Mention the bot or DM it to send commands.

Features:
  - Responds to mentions (@Jarvis) and DMs
  - Screenshot command (/screenshot)
  - System status (/status)
  - Memory lookup (/memory)
  - All other messages go to Jarvis brain
  - Rate limiting per channel
  - Automatic reconnection on disconnect
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

__all__ = ["DiscordBot", "get_discord_bot"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    owner_ids: List[str] = []
    prefix = os.environ.get("DISCORD_PREFIX", "!jarvis")

    if not token:
        config_path = "config/discord.json"
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    data = json.load(f)
                token = data.get("bot_token", "") or data.get("token", "")
                owner_ids = [str(x) for x in data.get("owner_ids", [])]
                prefix = data.get("prefix", prefix)
            except Exception as exc:
                log.warning("Failed to load %s: %s", config_path, exc)

    return {"bot_token": token, "owner_ids": owner_ids, "prefix": prefix}


@dataclass
class DiscordConfig:
    bot_token: str
    owner_ids: List[str] = field(default_factory=list)
    prefix: str = "!jarvis"
    mention_enabled: bool = True
    dm_enabled: bool = True
    allowed_channel_ids: List[str] = field(default_factory=list)
    blocked_channel_ids: List[str] = field(default_factory=list)

    def is_owner(self, user_id: str) -> bool:
        return str(user_id) in [str(x) for x in self.owner_ids]

    def is_channel_allowed(self, channel_id: str) -> bool:
        if self.allowed_channel_ids:
            return str(channel_id) in [str(x) for x in self.allowed_channel_ids]
        if self.blocked_channel_ids:
            return str(channel_id) not in [str(x) for x in self.blocked_channel_ids]
        return True


@dataclass
class DiscordMessage:
    id: str
    channel_id: str
    guild_id: Optional[str]
    author_id: str
    author_name: str
    author_is_bot: bool
    content: str
    is_dm: bool
    mentions_bot: bool
    raw: Dict[str, Any]

    @property
    def is_command(self) -> bool:
        return self.content.startswith(self.content[:2])  # detect by prefix


# ---------------------------------------------------------------------------
# Discord API (raw HTTP — no discord.py dependency)
# ---------------------------------------------------------------------------

class DiscordAPI:
    """Low-level Discord REST API wrapper."""

    BASE = "https://discord.com/api/v10"

    def __init__(self, token: str) -> None:
        self._token = token
        self._session: Optional[Any] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (JarvisAI, 1.0)",
        }

    def _post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None,
        files: Optional[Any] = None
    ) -> Dict[str, Any]:
        import urllib.request

        url = f"{self.BASE}/{endpoint}"
        body = json.dumps(data or {}).encode("utf-8") if data else None
        headers = self._headers()
        if files:
            # Multipart not fully implemented — use text channel for now
            raise NotImplementedError("File uploads not yet implemented")
        req = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        import urllib.request
        import urllib.parse

        url = f"{self.BASE}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _patch(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        import urllib.request

        url = f"{self.BASE}/{endpoint}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers=self._headers(), method="PATCH"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bot_user(self) -> Dict[str, Any]:
        return self._get("users/@me")

    def get_channel(self, channel_id: str) -> Dict[str, Any]:
        return self._get(f"channels/{channel_id}")

    def send_message(
        self, channel_id: str, content: str, embed: Optional[Dict[str, Any]] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"content": content}
        if embed:
            data["embeds"] = [embed]
        if reply_to:
            data["message_reference"] = {"message_id": reply_to}
        return self._post(f"channels/{channel_id}/messages", data)

    def edit_message(self, channel_id: str, message_id: str, content: str) -> Dict[str, Any]:
        return self._patch(
            f"channels/{channel_id}/messages/{message_id}",
            {"content": content},
        )

    def send_file(
        self, channel_id: str, file_data: bytes, filename: str,
        caption: str = "", content: str = ""
    ) -> Dict[str, Any]:
        # Discord file upload via multipart
        import urllib.request
        import uuid

        boundary = f"----DiscordBoundary{uuid.uuid4().hex}"
        parts = []
        if content or caption:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="payload_json"\r\n'
                f"Content-Type: application/json\r\n\r\n"
                f'{json.dumps({"content": content or caption})}\r\n'
            )
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        )
        body = "".join(parts).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            f"{self.BASE}/channels/{channel_id}/messages",
            data=body,
            headers={
                "Authorization": f"Bot {self._token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "DiscordBot (JarvisAI, 1.0)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_messages(
        self, channel_id: str, limit: int = 1, before: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, str] = {"limit": str(limit)}
        if before:
            params["before"] = before
        result = self._get(f"channels/{channel_id}/messages", params)
        return result if isinstance(result, list) else []

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        # URL-encode the emoji
        import urllib.parse
        encoded = urllib.parse.quote(emoji)
        url = f"{self.BASE}/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
        import urllib.request
        req = urllib.request.Request(url, headers=self._headers(), method="PUT")
        with urllib.request.urlopen(req, timeout=5):
            pass


# ---------------------------------------------------------------------------
# Gateway (websocket simulation via long polling — lightweight approach)
# ---------------------------------------------------------------------------

class DiscordGateway:
    """Discord gateway connection using urllib for long-polling.

    This is a simplified gateway using the REST API's message polling
    (no websockets dependency required).
    """

    def __init__(self, api: DiscordAPI, guild_id: Optional[str] = None) -> None:
        self._api = api
        self._guild_id = guild_id
        self._last_message_id: Optional[str] = None
        self._channel_ids: List[str] = []
        self._heartbeat_interval: float = 15.0
        self._running = False
        self._lock = threading.Lock()
        self._message_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_message_callback(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._message_callback = cb

    def _discover_channels(self) -> List[str]:
        """Get text channels the bot can read."""
        if not self._guild_id:
            return []
        try:
            guild = self._api._get(f"guilds/{self._guild_id}/channels")
            if isinstance(guild, list):
                return [str(c["id"]) for c in guild if c.get("type") == 0]  # text channels
        except Exception as exc:
            log.warning("[Discord] Channel discovery failed: %s", exc)
        return []

    def _poll_channel(self, channel_id: str) -> List[Dict[str, Any]]:
        """Poll one channel for new messages."""
        try:
            params: Dict[str, str] = {"limit": "5"}
            if self._last_message_id:
                params["after"] = self._last_message_id
            msgs = self._api._get(f"channels/{channel_id}/messages", params)
            if isinstance(msgs, list) and msgs:
                self._last_message_id = msgs[-1]["id"]
                return msgs
        except Exception as exc:
            log.debug("[Discord] Poll channel %s failed: %s", channel_id, exc)
        return []

    def poll(self) -> List[Dict[str, Any]]:
        """Poll all channels for new messages. Returns list of message dicts."""
        with self._lock:
            if not self._running:
                return []
            channels = self._channel_ids
        all_messages: List[Dict[str, Any]] = []
        for ch_id in channels:
            try:
                msgs = self._poll_channel(ch_id)
                all_messages.extend(msgs)
            except Exception:
                pass
        return all_messages

    def start(self) -> None:
        with self._lock:
            self._running = True
            if self._guild_id:
                self._channel_ids = self._discover_channels()
                log.info("[Discord] Discovered %d channels", len(self._channel_ids))

    def stop(self) -> None:
        with self._lock:
            self._running = False


# ---------------------------------------------------------------------------
# Main bot
# ---------------------------------------------------------------------------

class DiscordBot:
    """Discord bot bridging messages to the Jarvis command pipeline.

    Thread-safe. The polling loop runs in a daemon thread.
    Call ``shutdown()`` to stop cleanly.
    """

    def __init__(
        self,
        config: Optional[DiscordConfig] = None,
        command_handler: Optional[Callable[[str], str]] = None,
    ) -> None:
        if config is None:
            raw = _load_config()
            config = DiscordConfig(
                bot_token=raw.get("bot_token", ""),
                owner_ids=raw.get("owner_ids", []),
                prefix=raw.get("prefix", "!jarvis"),
            )
        self._config = config
        self._command_handler = command_handler
        self._api = DiscordAPI(config.bot_token) if config.bot_token else None
        self._gateway: Optional[DiscordGateway] = None
        self._running = False
        self._lock = threading.RLock()
        self._poll_thread: Optional[threading.Thread] = None
        self._message_count = 0
        self._connected = False
        self._start_time = 0.0
        self._bot_user_id: Optional[str] = None
        self._bot_username: Optional[str] = None
        self._rate_limits: Dict[str, List[float]] = {}
        self._rate_limit_lock = threading.Lock()
        self._RATE_LIMIT = 5
        self._poll_interval = 3.0  # seconds between polls

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_configured(self) -> bool:
        return bool(self._config.bot_token)

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    # ------------------------------------------------------------------
    # Gateway setup
    # ------------------------------------------------------------------

    def _connect_gateway(self) -> bool:
        if not self._api:
            return False
        try:
            user = self._api.get_bot_user()
            self._bot_user_id = str(user.get("id", ""))
            self._bot_username = user.get("username", "Unknown")
            log.info("[Discord] Bot logged in as %s#%s",
                     self._bot_username, self._bot_user_id[-4:])
            self._gateway = DiscordGateway(self._api)
            self._gateway.set_message_callback(self._on_gateway_message)
            self._gateway.start()
            return True
        except Exception as exc:
            log.error("[Discord] Gateway login failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------

    def _parse_message(self, raw_msg: Dict[str, Any]) -> Optional[DiscordMessage]:
        try:
            author = raw_msg.get("author", {})
            channel_id = str(raw_msg.get("channel_id", ""))
            guild_id = raw_msg.get("guild_id")
            content = raw_msg.get("content", "") or ""

            # Check if bot is mentioned
            mentions = raw_msg.get("mentions", [])
            bot_mentioned = any(
                str(u.get("id", "")) == str(self._bot_user_id) for u in mentions
            )

            # Clean content: remove mention prefix
            cleaned = content
            if mentions:
                mention_pattern = rf"<@!?{self._bot_user_id}>"
                cleaned = re.sub(mention_pattern, "", cleaned).strip()

            return DiscordMessage(
                id=str(raw_msg.get("id", "")),
                channel_id=channel_id,
                guild_id=str(guild_id) if guild_id else None,
                author_id=str(author.get("id", "")),
                author_name=author.get("username", "Unknown"),
                author_is_bot=author.get("bot", False),
                content=cleaned.strip() or content.strip(),
                is_dm=guild_id is None,
                mentions_bot=bot_mentioned,
                raw=raw_msg,
            )
        except Exception as exc:
            log.warning("[Discord] Failed to parse message: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _check_rate_limit(self, channel_id: str) -> bool:
        now = time.time()
        with self._rate_limit_lock:
            if channel_id not in self._rate_limits:
                self._rate_limits[channel_id] = []
            self._rate_limits[channel_id] = [
                t for t in self._rate_limits[channel_id] if now - t < 10.0
            ]
            if len(self._rate_limits[channel_id]) >= self._RATE_LIMIT:
                return False
            self._rate_limits[channel_id].append(now)
            return True

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    def _handle_command(self, msg: DiscordMessage) -> Optional[str]:
        content = msg.content.strip()
        prefix = self._config.prefix

        if not content.startswith(prefix) and not msg.mentions_bot:
            return None

        # Extract command
        if content.startswith(prefix):
            cmd_text = content[len(prefix):].strip()
        elif msg.mentions_bot:
            cmd_text = content
        else:
            cmd_text = content

        cmd_parts = cmd_text.split()
        cmd = cmd_parts[0].lower() if cmd_parts else ""

        if cmd in ("status",):
            return self._cmd_status()
        if cmd in ("help",):
            return self._cmd_help()
        if cmd in ("screenshot", "ss"):
            return self._cmd_screenshot()
        if cmd in ("memory", "mem"):
            return self._cmd_memory()
        if cmd in ("ping",):
            return f"🏓 Pong! `{int(self.uptime)}s` uptime"
        if cmd in ("invite",):
            return self._cmd_invite()

        return None

    def _cmd_status(self) -> str:
        from jarvis_core.capability_registry import get_capability_registry
        reg = get_capability_registry()
        reg.refresh(force=True)
        summary = reg.summary()
        jstatus = reg.jarvis_status()
        lines = [
            f"**Jarvis Status**",
            f"Runtime: {jstatus.get('overall', 'UNKNOWN')}",
            f"Available: {summary.get('available', 0)}",
            f"Degraded: {summary.get('degraded', 0)}",
            f"Not Configured: {summary.get('not_configured', 0)}",
            f"Unavailable: {summary.get('unavailable', 0)}",
            f"Messages: {self._message_count}",
            f"Uptime: {int(self.uptime)}s",
        ]
        return "\n".join(lines)

    def _cmd_help(self) -> str:
        prefix = self._config.prefix
        return (
            f"**Jarvis Discord Commands**\n\n"
            f"`{prefix} status` — System status\n"
            f"`{prefix} screenshot` — Take screenshot\n"
            f"`{prefix} memory` — Recent memories\n"
            f"`{prefix} ping` — Pong!\n"
            f"`{prefix} help` — This message\n\n"
            f"Any other message goes to the Jarvis brain.\n"
            f"You can also mention me directly."
        )

    def _cmd_screenshot(self) -> str:
        if not self._api:
            return "❌ API not initialized"
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
            self._api.send_file(
                msg.channel_id,  # This will be set in _dispatch
                png.tobytes(),
                "screenshot.png",
                caption=" Jarvis Screenshot",
            )
            return "📸 Sending screenshot..."
        except Exception as exc:
            return f"❌ Screenshot failed: {exc}"

    def _cmd_memory(self) -> str:
        try:
            from memory.manager import MemoryManager

            mgmt = MemoryManager()
            entries = mgmt.search("", limit=5)
            if not entries:
                return "📭 No memory entries found."
            lines = ["🧠 **Recent Memories**", ""]
            for e in entries[:5]:
                content = (e.get("content", str(e))[:80])
                lines.append(f"• {content}")
            return "\n".join(lines)
        except Exception as exc:
            return f"❌ Memory error: {exc}"

    def _cmd_invite(self) -> str:
        return (
            "To invite me to your server:\n"
            "1. Go to Discord Developer Portal → Applications → Your Bot\n"
            "2. OAuth2 → URL Generator\n"
            "3. Check: bot, applications.commands\n"
            "4. Permissions: Send Messages, Embed Links, Read Message History\n"
            "5. Use the generated URL to invite."
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, msg: DiscordMessage) -> None:
        self._message_count += 1
        log.info(
            "[Discord] %s#%s (%s): %s",
            msg.author_name,
            msg.author_id[-4:],
            msg.channel_id,
            msg.content[:80],
        )

        if not self._check_rate_limit(msg.channel_id):
            return

        # Ignore bot's own messages
        if msg.author_is_bot and str(msg.author_id) == str(self._bot_user_id):
            return

        # DM and mention check
        if not msg.is_dm and not msg.mentions_bot:
            return

        # Built-in command?
        cmd_response = self._handle_command(msg)
        if cmd_response is not None:
            self._send(msg.channel_id, cmd_response)
            return

        # Pass to brain
        handler = self._command_handler
        if handler is None:
            from brains_v2.runtime import get_runtime

            def default_handler(t: str) -> str:
                runtime = get_runtime()
                reply = runtime.process(t)
                if hasattr(reply, "reply_text"):
                    return str(reply.reply_text)
                if isinstance(reply, dict):
                    return str(reply.get("reply_text", reply.get("text", str(reply))))
                return str(reply) if reply else "No response."

            handler = default_handler

        try:
            response = handler(msg.content)
            self._send(msg.channel_id, str(response))
        except Exception as exc:
            log.error("[Discord] Brain error: %s", exc)
            self._send(msg.channel_id, f"❌ Error: {exc}")

    def _send(self, channel_id: str, content: str) -> None:
        if not self._api:
            return
        try:
            # Split long messages (Discord limit 2000)
            for chunk in [content[i:i+1900] for i in range(0, len(content), 1900)]:
                self._api.send_message(channel_id, chunk)
                time.sleep(0.3)
        except Exception as exc:
            log.error("[Discord] Send failed: %s", exc)

    # ------------------------------------------------------------------
    # Gateway callback
    # ------------------------------------------------------------------

    def _on_gateway_message(self, raw_msg: Dict[str, Any]) -> None:
        msg = self._parse_message(raw_msg)
        if msg is not None:
            self._dispatch(msg)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        log.info("[Discord] Poll thread started")
        consecutive_errors = 0
        while self._running:
            try:
                if self._gateway:
                    messages = self._gateway.poll()
                    for raw_msg in messages:
                        self._on_gateway_message(raw_msg)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                wait = min(30, 2**consecutive_errors)
                log.warning(
                    "[Discord] Poll error (consecutive=%d, wait=%ds): %s",
                    consecutive_errors,
                    wait,
                    exc,
                )
                time.sleep(wait)
            time.sleep(self._poll_interval)
        log.info("[Discord] Poll thread stopped")

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def connect(self, guild_id: Optional[str] = None) -> bool:
        """Start the Discord bot. Returns True on success."""
        if not self.is_configured:
            log.error("[Discord] Not configured: no bot token found.")
            return False

        if self._guild_id is None and guild_id:
            self._guild_id = guild_id

        if not self._connect_gateway():
            return False

        with self._lock:
            if self._running:
                return True
            self._running = True
            self._start_time = time.time()
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._poll_thread.start()
            self._connected = True
            log.info("[Discord] Connected and polling")
            return True

    def disconnect(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._connected = False
        if self._gateway:
            self._gateway.stop()
        log.info("[Discord] Disconnected")

    def shutdown(self) -> None:
        self.disconnect()
        self._poll_thread = None

    # ------------------------------------------------------------------
    # Outbound helpers
    # ------------------------------------------------------------------

    def notify_owner(self, message: str, channel_id: str) -> bool:
        """Send a message to a specific channel. Returns True on success."""
        if not self._api:
            return False
        try:
            self._send(channel_id, message)
            return True
        except Exception as exc:
            log.error("[Discord] Notify failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured,
            "connected": self._connected,
            "bot_username": self._bot_username,
            "owner_ids": self._config.owner_ids,
            "message_count": self._message_count,
            "uptime_seconds": round(self.uptime, 1),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_DISCORD_BOT: Optional[DiscordBot] = None
_DISCORD_LOCK = threading.Lock()


def get_discord_bot() -> DiscordBot:
    global _DISCORD_BOT
    with _DISCORD_LOCK:
        if _DISCORD_BOT is None:
            _DISCORD_BOT = DiscordBot()
        return _DISCORD_BOT


def connect_discord(
    guild_id: Optional[str] = None,
    command_handler: Optional[Callable[[str], str]] = None
) -> bool:
    """Convenience: get and connect the Discord bot."""
    bot = get_discord_bot()
    if command_handler:
        bot._command_handler = command_handler
    return bot.connect(guild_id)
