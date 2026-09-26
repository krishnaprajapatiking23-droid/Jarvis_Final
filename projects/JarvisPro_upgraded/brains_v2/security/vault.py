"""Encrypted secret store (roadmap section 24: Secret Protection)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from brains_v2.security.encryption import EncryptionError, encryptor

__all__ = ["Vault", "vault"]

STORE = os.path.join("data", "vault.json")
REDACTED = "********"


class Vault:
    """Named secrets, encrypted at rest, never echoed back in plain text."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or STORE
        self._items: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                self._items = stored
        except (OSError, json.JSONDecodeError):
            self._items = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._items, handle, indent=2)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def put(self, name: str, secret: Any, note: str = "") -> Dict[str, Any]:
        name = str(name).strip()
        if not name:
            return {"success": False, "error": "a secret needs a name"}
        self._items[name] = {
            "payload": encryptor.encrypt(secret),
            "note": note,
            "backend": encryptor.backend,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        self.save()
        return {"success": True, "name": name}

    def get(self, name: str) -> Dict[str, Any]:
        entry = self._items.get(name)
        if entry is None:
            return {"success": False, "error": "no secret called %r" % name}
        try:
            return {"success": True, "name": name,
                    "secret": encryptor.decrypt(entry["payload"])}
        except EncryptionError as error:
            return {"success": False, "error": str(error)}

    def delete(self, name: str) -> Dict[str, Any]:
        if self._items.pop(name, None) is None:
            return {"success": False, "error": "no secret called %r" % name}
        self.save()
        return {"success": True}

    def names(self) -> List[str]:
        return sorted(self._items)

    def listing(self) -> List[Dict[str, str]]:
        """Metadata only -- the values are never included."""
        return [{"name": name, "note": entry.get("note", ""),
                 "updated": entry.get("updated", ""), "value": REDACTED}
                for name, entry in sorted(self._items.items())]


vault = Vault()
