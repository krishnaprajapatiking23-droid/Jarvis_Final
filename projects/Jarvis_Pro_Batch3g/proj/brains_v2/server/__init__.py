"""Companion server package; optional web dependencies load lazily."""
from .auth import auth
from .client_manager import clients
from .heartbeat import heartbeat
from .encryption import encryption
from .websocket import websocket

def create_server():
    from .api import create_server as create
    return create()

__all__ = ["auth", "clients", "heartbeat", "encryption", "websocket", "create_server"]
