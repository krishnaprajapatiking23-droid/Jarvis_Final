"""Import-safe stand-in for the optional ``ollama`` package.

BUG FIX: eight modules did a bare top-level ``import ollama``
(``ai/manager.py``, ``ai/action_classifier.py``, ``ai/brain.py``,
``business/ai.py``, ``business/profit.py``, ``vision/image_reader.py``,
``brains_v2/ai/intent_engine.py``, ``core/command_router.py``). On any machine
without the package installed, importing *any* of them raised
ModuleNotFoundError, which cascaded: ``core.router`` -> ``missions.manager``
-> ``missions.executor`` -> ``business.manager`` -> ``business.ai`` -> dead.

``brains_v2/llm/provider.py`` already imported ollama lazily and handled its
absence. This module applies that same discipline everywhere else: the real
package is used when present, and otherwise calls raise
:class:`OllamaUnavailable` -- a normal exception the callers already catch --
instead of breaking the import graph.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ollama", "OllamaUnavailable", "available"]


class OllamaUnavailable(RuntimeError):
    """Raised when ollama is called but the package is not installed."""


try:  # pragma: no cover - depends on the host environment
    import ollama as _real_ollama
except Exception:  # ImportError, and anything the package raises on import
    _real_ollama = None


class _MissingOllama:
    """Stub that fails loudly at call time rather than at import time."""

    __slots__ = ()

    _MESSAGE = (
        "the 'ollama' package is not installed; "
        "run 'pip install ollama' and start 'ollama serve' to enable "
        "model-backed answers"
    )

    def __getattr__(self, name: str) -> Any:
        def _unavailable(*args: Any, **kwargs: Any) -> Any:
            raise OllamaUnavailable(self._MESSAGE)

        _unavailable.__name__ = name
        return _unavailable

    def __bool__(self) -> bool:
        return False


ollama = _real_ollama if _real_ollama is not None else _MissingOllama()


def available() -> bool:
    """True when the real ollama package could be imported."""
    return _real_ollama is not None
