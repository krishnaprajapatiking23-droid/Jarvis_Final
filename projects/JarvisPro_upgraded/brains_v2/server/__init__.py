"""Companion server package; optional web dependencies load lazily."""
from .auth import auth
from .client_manager import clients
from .config import config
from .heartbeat import heartbeat
from .encryption import encryption
from .websocket import websocket

def create_server():
    from .api import create_server as create
    return create()

# BUG FIX: manual_demos/demo_sprint_a2.py does
# ``from brains_v2.server import *`` and then reads ``config.VERSION``.
# ``config.py`` already defines a ``config`` singleton with a ``VERSION``
# attribute, but it was never imported here, so ``config`` did not exist in
# this package's namespace and the demo raised
# NameError: name 'config' is not defined.
__all__ = ["auth", "clients", "config", "heartbeat", "encryption", "websocket",
           "create_server"]
