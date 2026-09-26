"""OAuth 2.0 authorization-code flow with PKCE (BUG 5).

Two modes, never an indefinite wait:

* ``browser``  - open a system browser and serve one local callback request.
* ``manual``   - print the URL and read the pasted code/redirect URL. Chosen
  automatically when the environment is headless or the browser cannot be
  launched (Docker, SSH, CI, service mode).

Every wait has a finite timeout (``JARVIS_OAUTH_TIMEOUT``, default 300s).
On expiry the flow raises :class:`OAuthTimeout` with the message
"Authentication timed out." State validation, PKCE S256, token validation,
callback path validation and 0600 token storage are all retained.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import socket
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

__all__ = [
    "OAuthError",
    "OAuthTimeout",
    "OAuthToken",
    "TokenStore",
    "AuthorizationCodeFlow",
    "OAuthClient",
    "TIMEOUT_MESSAGE",
    "DEFAULT_TIMEOUT",
    "CALLBACK_PATH",
    "headless",
]

log = logging.getLogger(__name__)

TIMEOUT_MESSAGE = "Authentication timed out."
CALLBACK_PATH = "/callback"


def _default_timeout() -> float:
    raw = os.environ.get("JARVIS_OAUTH_TIMEOUT", "300")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 300.0
    return value if value > 0 else 300.0


DEFAULT_TIMEOUT = _default_timeout()


class OAuthError(RuntimeError):
    """Any OAuth failure that is not a timeout."""


class OAuthTimeout(OAuthError):
    """Raised when authentication does not complete in time."""

    def __init__(self, message: str = TIMEOUT_MESSAGE) -> None:
        super().__init__(message)


def headless() -> bool:
    """Best-effort detection of an environment without a usable browser."""
    if os.environ.get("JARVIS_OAUTH_HEADLESS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if os.environ.get("CI") or os.environ.get("JARVIS_TESTING"):
        return True
    if not sys.stdin or not sys.stdin.isatty():
        stdin_interactive = False
    else:
        stdin_interactive = True
    if sys.platform.startswith("linux"):
        display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        if not display:
            return True
    if os.path.exists("/.dockerenv"):
        return True
    if os.environ.get("SSH_CONNECTION") and not stdin_interactive:
        return True
    return False


def _free_port() -> int:
    """Ask the OS for an unused loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class OAuthToken:
    """A validated token response."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    scope: str = ""
    expires_at: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        if not self.expires_at:
            return False
        return time.time() >= self.expires_at - 30

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_response(cls, payload: Dict[str, Any]) -> "OAuthToken":
        """Validate a token endpoint response."""
        if not isinstance(payload, dict):
            raise OAuthError("token response was not a JSON object")
        if payload.get("error"):
            raise OAuthError(
                "token endpoint error: %s" % payload.get("error_description")
                or payload["error"]
            )
        access = str(payload.get("access_token") or "").strip()
        if not access:
            raise OAuthError("token response did not contain an access_token")
        expires_in = payload.get("expires_in")
        expires_at = 0.0
        if expires_in:
            try:
                expires_at = time.time() + float(expires_in)
            except (TypeError, ValueError):
                expires_at = 0.0
        return cls(
            access_token=access,
            token_type=str(payload.get("token_type") or "Bearer"),
            refresh_token=str(payload.get("refresh_token") or ""),
            scope=str(payload.get("scope") or ""),
            expires_at=expires_at,
            raw=dict(payload),
        )


class TokenStore:
    """Stores tokens on disk with owner-only permissions."""

    def __init__(self, path: Any = "data/oauth_tokens.json") -> None:
        self.path = Path(path)

    def _read(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception as error:
            log.warning("could not read token store: %r", error)
            return {}

    def save(self, provider: str, token: OAuthToken) -> None:
        data = self._read()
        data[str(provider)] = token.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError as error:
            log.debug("could not tighten token file permissions: %r", error)

    def load(self, provider: str) -> Optional[OAuthToken]:
        payload = self._read().get(str(provider))
        if not isinstance(payload, dict) or not payload.get("access_token"):
            return None
        return OAuthToken(
            access_token=str(payload["access_token"]),
            token_type=str(payload.get("token_type") or "Bearer"),
            refresh_token=str(payload.get("refresh_token") or ""),
            scope=str(payload.get("scope") or ""),
            expires_at=float(payload.get("expires_at") or 0.0),
            raw=dict(payload),
        )

    def clear(self, provider: str) -> None:
        data = self._read()
        if data.pop(str(provider), None) is not None:
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class _CallbackHandler(BaseHTTPRequestHandler):
    """Serves exactly one redirect request and records the query."""

    result: Dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.parse_qs(parsed.query)
        type(self).result = {key: values[0] for key, values in query.items()}
        body = b"Authentication complete. You can close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        """Silence the default stderr access log."""


class AuthorizationCodeFlow:
    """Authorization-code + PKCE flow with browser and manual modes."""

    def __init__(
        self,
        client_id: str,
        authorization_endpoint: str,
        token_endpoint: str,
        client_secret: str = "",
        scopes: Sequence[str] = (),
        redirect_port: int = 0,
        timeout: float = DEFAULT_TIMEOUT,
        mode: str = "auto",
        prompt: Optional[Callable[[str], str]] = None,
        opener: Optional[Callable[[str], bool]] = None,
    ) -> None:
        if not client_id:
            raise OAuthError("client_id is required")
        if not authorization_endpoint or not token_endpoint:
            raise OAuthError("authorization and token endpoints are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.scopes = list(scopes)
        self.timeout = float(timeout) if float(timeout) > 0 else DEFAULT_TIMEOUT
        self.mode = mode
        self.prompt = prompt
        self.opener = opener
        self.redirect_port = int(redirect_port) or _free_port()
        self.state = secrets.token_urlsafe(24)
        self.verifier = secrets.token_urlsafe(64)
        self.challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(self.verifier.encode("ascii")).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )

    # -------------------------------------------------------------- helpers
    @property
    def redirect_uri(self) -> str:
        return "http://127.0.0.1:%d%s" % (self.redirect_port, CALLBACK_PATH)

    def resolve_mode(self) -> str:
        """Decide between the browser and manual flows."""
        if self.mode in ("browser", "manual"):
            return self.mode
        return "manual" if headless() else "browser"

    def authorization_url(self) -> str:
        """Build the provider authorization URL (PKCE S256)."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": self.state,
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
        }
        if self.scopes:
            params["scope"] = " ".join(self.scopes)
        separator = "&" if "?" in self.authorization_endpoint else "?"
        return self.authorization_endpoint + separator + urllib.parse.urlencode(params)

    def _validate(self, query: Dict[str, str]) -> str:
        """Validate the callback payload and return the code."""
        if query.get("error"):
            raise OAuthError(
                "authorization denied: %s"
                % (query.get("error_description") or query["error"])
            )
        if query.get("state") != self.state:
            raise OAuthError("state mismatch: possible CSRF, aborting")
        code = str(query.get("code") or "").strip()
        if not code:
            raise OAuthError("callback did not contain an authorization code")
        return code

    # ----------------------------------------------------------------- waits
    def _wait_for_callback(self) -> str:
        """Serve the loopback callback until the code arrives or time runs out."""
        _CallbackHandler.result = {}
        deadline = time.monotonic() + self.timeout
        try:
            server = HTTPServer(("127.0.0.1", self.redirect_port), _CallbackHandler)
        except OSError as error:
            raise OAuthError("could not start the callback server: %r" % error)
        server.timeout = 1.0
        try:
            while time.monotonic() < deadline:
                server.handle_request()
                if _CallbackHandler.result:
                    return self._validate(dict(_CallbackHandler.result))
        finally:
            server.server_close()
        raise OAuthTimeout()

    def _manual_code(self) -> str:
        """Print the URL and read the pasted code or redirect URL."""
        url = self.authorization_url()
        print("\nOpen this URL in a browser to authorize Jarvis:\n")
        print(url)
        print("\nThen paste the authorization code (or the full redirect URL).")
        reader = self.prompt
        if reader is None:
            if not sys.stdin or not sys.stdin.isatty():
                raise OAuthTimeout()
            reader = input
        try:
            raw = reader("Authorization code: ")
        except (EOFError, KeyboardInterrupt):
            raise OAuthTimeout()
        pasted = str(raw or "").strip()
        if not pasted:
            raise OAuthError("no authorization code was provided")
        if "?" in pasted or pasted.lower().startswith("http"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
            return self._validate({k: v[0] for k, v in query.items()})
        return pasted

    # ------------------------------------------------------------- execution
    def exchange(self, code: str) -> OAuthToken:
        """Exchange the authorization code for a validated token."""
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self.verifier,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        request = urllib.request.Request(
            self.token_endpoint,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except OAuthError:
            raise
        except Exception as error:
            raise OAuthError("token exchange failed: %r" % error)
        return OAuthToken.from_response(body)

    def run(self) -> OAuthToken:
        """Execute the whole flow in the appropriate mode."""
        mode = self.resolve_mode()
        if mode == "browser":
            url = self.authorization_url()
            opened = False
            try:
                if self.opener is not None:
                    opened = bool(self.opener(url))
                else:
                    import webbrowser

                    opened = bool(webbrowser.open(url))
            except Exception as error:
                log.info("browser launch failed (%r); using manual mode", error)
                opened = False
            if not opened:
                log.info("no usable browser; switching to manual OAuth mode")
                return self.exchange(self._manual_code())
            print("Waiting for authorization (timeout %ds)..." % int(self.timeout))
            return self.exchange(self._wait_for_callback())
        return self.exchange(self._manual_code())


class OAuthClient:
    """Convenience wrapper: cached tokens, refresh, then interactive flow."""

    def __init__(
        self,
        provider: str,
        client_id: str = "",
        client_secret: str = "",
        authorization_endpoint: str = "",
        token_endpoint: str = "",
        scopes: Sequence[str] = (),
        store: Optional[TokenStore] = None,
        timeout: float = DEFAULT_TIMEOUT,
        mode: str = "auto",
    ) -> None:
        self.provider = provider
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.scopes = list(scopes)
        self.store = store or TokenStore()
        self.timeout = timeout
        self.mode = mode

    def refresh(self, token: OAuthToken) -> OAuthToken:
        """Refresh an expired token."""
        if not token.refresh_token:
            raise OAuthError("no refresh token available")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        request = urllib.request.Request(
            self.token_endpoint,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except Exception as error:
            raise OAuthError("token refresh failed: %r" % error)
        refreshed = OAuthToken.from_response(body)
        if not refreshed.refresh_token:
            refreshed.refresh_token = token.refresh_token
        self.store.save(self.provider, refreshed)
        return refreshed

    def authorize(self, interactive: bool = True) -> OAuthToken:
        """Return a usable token, authorizing only when necessary."""
        token = self.store.load(self.provider)
        if token and not token.expired:
            return token
        if token and token.refresh_token:
            try:
                return self.refresh(token)
            except OAuthError as error:
                log.info("refresh failed (%s); re-authorizing", error)
        if not interactive:
            raise OAuthError(
                "%s is not authorized; run the OAuth flow first" % self.provider
            )
        flow = AuthorizationCodeFlow(
            client_id=self.client_id,
            authorization_endpoint=self.authorization_endpoint,
            token_endpoint=self.token_endpoint,
            client_secret=self.client_secret,
            scopes=self.scopes,
            timeout=self.timeout,
            mode=self.mode,
        )
        fresh = flow.run()
        self.store.save(self.provider, fresh)
        return fresh

    def access_token(self) -> str:
        """Non-interactive accessor used by the integrations."""
        return self.authorize(interactive=False).access_token
