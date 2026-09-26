"""Jarvis API layer.

Client -> API -> Authentication -> Command/Task service -> Jarvis core -> Managers

`service.ApiService` is transport agnostic and holds auth, authorization,
validation, rate limiting, tracing and events. `server.ApiServer` is the HTTP
adapter, `ws` holds WebSocket framing. No business logic lives here.

The legacy provider helpers (ollama, openrouter, search, weather) remain in
this package and are imported lazily so a missing optional dependency cannot
break the API layer.
"""

from .service import (
    ApiError,
    ApiService,
    EventBus,
    NOT_CONFIGURED,
    OK,
    RateLimiter,
    Subscription,
    UNAVAILABLE,
    new_trace_id,
    validate,
)

__all__ = [
    "ApiService",
    "ApiError",
    "EventBus",
    "Subscription",
    "RateLimiter",
    "validate",
    "new_trace_id",
    "OK",
    "UNAVAILABLE",
    "NOT_CONFIGURED",
]


def make_server(service, host="127.0.0.1", port=8787):
    """Build the HTTP adapter. Imported lazily to keep import cost low."""
    from .server import ApiServer

    return ApiServer(service, host=host, port=port)
