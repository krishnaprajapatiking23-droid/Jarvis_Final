"""Owner identity and authentication state (roadmap section 24)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

__all__ = ["Owner", "owner"]

STORE = os.path.join("data", "owner.json")
ITERATIONS = 200_000


def _hash(password: str, salt: bytes) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                  salt, ITERATIONS)
    return derived.hex()


class Owner:
    """Who Jarvis belongs to, and whether they are currently authenticated."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or STORE
        self._data: Dict[str, Any] = {}
        self._authenticated = False
        self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    stored = json.load(handle)
                if isinstance(stored, dict):
                    self._data = stored
            except (OSError, json.JSONDecodeError):
                self._data = {}
        return self._data

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

    # -- identity ----------------------------------------------------
    @property
    def name(self) -> str:
        return str(self._data.get("name", "")) or ""

    def registered(self) -> bool:
        return bool(self._data.get("name"))

    def register(self, name: str, password: str = "") -> Dict[str, Any]:
        name = str(name).strip()
        if not name:
            return {"success": False, "error": "an owner needs a name"}

        self._data["name"] = name
        self._data["registered_at"] = datetime.now().isoformat(timespec="seconds")

        if password:
            salt = secrets.token_bytes(16)
            self._data["salt"] = salt.hex()
            self._data["hash"] = _hash(password, salt)

        self.save()
        self._authenticated = True
        return {"success": True, "name": name}

    # -- authentication ----------------------------------------------
    def requires_password(self) -> bool:
        return bool(self._data.get("hash"))

    def authenticate(self, password: str = "") -> bool:
        if not self.registered():
            return False
        if not self.requires_password():
            self._authenticated = True
            return True
        salt = bytes.fromhex(str(self._data.get("salt", "")))
        expected = str(self._data.get("hash", ""))
        self._authenticated = secrets.compare_digest(_hash(password, salt), expected)
        return self._authenticated

    def authenticated(self) -> bool:
        return self._authenticated or not self.requires_password()

    def lock(self) -> None:
        self._authenticated = False

    def forget(self) -> None:
        self._data = {}
        self._authenticated = False
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "registered": self.registered(),
                "password_protected": self.requires_password(),
                "authenticated": self.authenticated()}


owner = Owner()
