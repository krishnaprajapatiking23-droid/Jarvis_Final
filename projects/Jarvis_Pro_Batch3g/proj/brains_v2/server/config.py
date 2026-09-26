"""
Jarvis Server Configuration
"""

from dataclasses import dataclass


@dataclass
class ServerConfig:

    HOST = "0.0.0.0"

    PORT = 5000

    DEBUG = False

    SECRET_KEY = "JARVIS_V2_KRISHNA"

    API_PREFIX = "/api"

    MAX_CLIENTS = 5

    HEARTBEAT_SECONDS = 10

    BUFFER_SIZE = 4096

    VERSION = "2.0"


config = ServerConfig()