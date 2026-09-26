"""Conversational helpers for the AI layer.

Adapter over the canonical conversation system in ``conversation/`` so the AI
package has one supported entry point instead of a second implementation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["ConversationAdapter", "conversation_adapter", "understand", "reply"]

log = logging.getLogger("jarvis.ai.conversation")


class ConversationAdapter:
    """Understand a turn and compose a reply through the conversation engine."""

    def __init__(self) -> None:
        self._engine = None

    def engine(self) -> Optional[Any]:
        if self._engine is None:
            try:
                from conversation.conversation_engine import conversation_engine

                self._engine = conversation_engine
            except Exception as error:
                log.info("conversation engine unavailable: %s", error)
                return None
        return self._engine

    def understand(self, text: str) -> Dict[str, Any]:
        engine = self.engine()
        if engine is None:
            return {"text": text, "command": text, "handled": False,
                    "detail": "conversation engine unavailable"}
        try:
            understanding = engine.understand(text)
        except Exception as error:
            return {"text": text, "command": text, "handled": False,
                    "detail": "%s: %s" % (type(error).__name__, error)}
        return understanding.to_dict()

    def reply(self, text: str, answer: str, action: str = "") -> str:
        engine = self.engine()
        if engine is None:
            return answer
        try:
            understanding = engine.understand(text)
            return engine.commit(understanding, answer, action)
        except Exception as error:
            log.info("reply composition failed: %s", error)
            return answer

    def prompt(self, text: str) -> str:
        engine = self.engine()
        if engine is None:
            return text
        try:
            return engine.prompt(engine.understand(text))
        except Exception:
            return text


conversation_adapter = ConversationAdapter()


def understand(text: str) -> Dict[str, Any]:
    return conversation_adapter.understand(text)


def reply(text: str, answer: str, action: str = "") -> str:
    return conversation_adapter.reply(text, answer, action)
