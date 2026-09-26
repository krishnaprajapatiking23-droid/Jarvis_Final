"""
Jarvis Encryption Manager
"""

import hashlib
import secrets


class EncryptionManager:

    def __init__(self):

        self.algorithm = "sha256"

    def hash(self, text):

        return hashlib.sha256(

            text.encode()

        ).hexdigest()

    def generate_key(self):

        return secrets.token_hex(32)

    def verify(

        self,

        text,

        hashed

    ):

        return self.hash(text) == hashed


encryption = EncryptionManager()