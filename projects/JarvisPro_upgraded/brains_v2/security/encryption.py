"""Local encryption for secrets at rest (roadmap section 24).

Uses the ``cryptography`` package when installed (AES via Fernet) and falls
back to a keyed HMAC-based stream cipher from the standard library so secrets
are never written in plain text just because an optional package is missing.
The fallback is clearly labelled in the payload so it can be migrated later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Optional

__all__ = ["Encryptor", "encryptor", "encrypt", "decrypt", "EncryptionError"]

KEY_FILE = os.path.join("data", ".jarvis_key")


class EncryptionError(RuntimeError):
    """Raised when a payload cannot be decrypted."""


def _load_or_create_key(path: str = KEY_FILE) -> bytes:
    if os.path.exists(path):
        with open(path, "rb") as handle:
            key = handle.read().strip()
            if len(key) >= 32:
                return key
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    with open(path, "wb") as handle:
        handle.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class Encryptor:
    """Symmetric encryption for values stored on disk."""

    def __init__(self, key: Optional[bytes] = None):
        self.key = key or _load_or_create_key()
        self._fernet = None
        try:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(self.key)
        except Exception:
            self._fernet = None

    @property
    def backend(self) -> str:
        return "fernet" if self._fernet is not None else "hmac-stream"

    # -- stdlib fallback --------------------------------------------
    def _keystream(self, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block = hmac.new(self.key, nonce + counter.to_bytes(4, "big"),
                             hashlib.sha256).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def encrypt(self, value: Any) -> str:
        raw = json.dumps(value).encode("utf-8")

        if self._fernet is not None:
            return "f1:" + self._fernet.encrypt(raw).decode("ascii")

        nonce = secrets.token_bytes(16)
        cipher = bytes(a ^ b for a, b in zip(raw, self._keystream(nonce, len(raw))))
        tag = hmac.new(self.key, nonce + cipher, hashlib.sha256).digest()[:16]
        payload = base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")
        return "h1:" + payload

    def decrypt(self, payload: str) -> Any:
        text = str(payload or "")

        if text.startswith("f1:"):
            if self._fernet is None:
                raise EncryptionError(
                    "this secret needs the 'cryptography' package to read")
            raw = self._fernet.decrypt(text[3:].encode("ascii"))
            return json.loads(raw.decode("utf-8"))

        if text.startswith("h1:"):
            blob = base64.urlsafe_b64decode(text[3:].encode("ascii"))
            nonce, tag, cipher = blob[:16], blob[16:32], blob[32:]
            expected = hmac.new(self.key, nonce + cipher, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(tag, expected):
                raise EncryptionError("secret failed its integrity check")
            raw = bytes(a ^ b for a, b in zip(cipher, self._keystream(nonce, len(cipher))))
            return json.loads(raw.decode("utf-8"))

        raise EncryptionError("unrecognised payload format")


encryptor = Encryptor()


def encrypt(value: Any) -> str:
    return encryptor.encrypt(value)


def decrypt(payload: str) -> Any:
    return encryptor.decrypt(payload)
