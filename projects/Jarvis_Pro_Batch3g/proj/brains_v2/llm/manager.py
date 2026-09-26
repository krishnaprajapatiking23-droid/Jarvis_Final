"""
AI Brain entry point.

Pipeline for one knowledge/chat turn:

    command + engine context
        -> prompt_builder.build()          (personality + conversation context)
        -> response_generator.generate()   (plan, directives, sampling, quality gate)
        -> OllamaProvider.generate()       (the actual model call)

The variation layer is *between* the brain and the output, so the same
question asked twice reaches the model with different directives, a
different structure and a different seed, and the draft is checked
against what JARVIS already said before it is returned.
"""

import logging

from brains_v2.llm.ollama_provider import OllamaProvider
from brains_v2.llm.prompt_builder import build
from brains_v2.dialogue_memory import dialogue_memory
from conversation.output_sanitizer import final_user_response
from brains_v2.llm.fallback import respond as fallback_respond

log = logging.getLogger("jarvis.llm.manager")

provider = OllamaProvider()

OFFLINE = "Ollama is offline."

UNAVAILABLE = (
    "I could not put together a clean answer for that one. "
    "Ask me again and I will have another go."
)


def _final(text):
    """FINAL_USER_RESPONSE: the only exit for a model reply."""

    result = final_user_response(
        text,
        model=str(getattr(provider, "model", "") or ""),
    )

    if result.final_text:
        if result.leaked:
            log.info("[RESPONSE] sanitized=true model=%s", result.model)

        return result.final_text

    log.warning(
        "[RESPONSE] no deliverable answer (reason=%s leaked=%s)",
        result.reason,
        result.leaked,
    )

    return UNAVAILABLE


def _understanding():
    """The Conversation System's reading of the current turn, if any."""

    try:

        from conversation.conversation_engine import conversation_engine

        return conversation_engine.last_understanding

    except Exception:

        return None


def ask(command, context="", options=None):
    """Answer ``command`` with the local model.

    ``options`` may carry explicit generation parameters; when omitted the
    style controller chooses them from the response plan.
    """

    try:
        available = provider.available()
    except Exception as error:
        provider.last_error = f"availability check failed: {type(error).__name__}: {error}"
        log.exception(provider.last_error)
        available = False

    if not available:
        return fallback_respond(command, getattr(provider, "last_error", "offline"))

    history = dialogue_memory.recent()

    base_prompt = build(command, history, context)

    def call(prompt, generation_options=None):
        """Model call used by the response generator (and as fallback)."""

        merged = dict(generation_options or {})

        if options:

            merged.update(options)

        try:

            return provider.generate(prompt, merged or None)

        except TypeError:

            # An older provider (or a stale copy left over from a partial
            # update) accepts the prompt only.  Answer anyway instead of
            # failing the whole turn.
            log.warning(
                "provider does not accept generation options; "
                "falling back to a plain call"
            )

            return provider.generate(prompt)

    understanding = _understanding()

    try:

        from conversation.response_generator import response_generator

        reply = response_generator.generate(

            command,

            ask=call,

            base_prompt=base_prompt,

            understanding=understanding,

            session_id=str(getattr(understanding, "session_id", "") or ""),

            turn=int(getattr(understanding, "turn", 0) or 0),

        )

    except Exception as error:

        log.warning("response variation layer failed: %s", error)

        reply = ""

    if reply:

        return _final(reply)

    # The variation layer produced nothing (model empty or unavailable):
    # fall back to a plain single call so JARVIS still answers.
    try:
        return _final(call(base_prompt))
    except Exception as error:
        provider.last_error = f"generation failed: {type(error).__name__}: {error}"
        log.exception(provider.last_error)
        return fallback_respond(command, provider.last_error)
