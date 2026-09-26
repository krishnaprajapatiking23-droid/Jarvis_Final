"""
LLM Provider (simple direct wrapper)

Used by the coding manager and other helpers that want a one-shot model
call without the full conversation pipeline.

Two things changed for the response-variation work:
  * ``ollama`` is imported lazily, so importing this module (and anything
    that depends on it) no longer fails on machines without the package.
  * ``ask()`` accepts generation ``options`` - temperature, top_p, seed,
    repeat_penalty - so callers can control determinism instead of always
    getting the model defaults.
"""

import logging

log = logging.getLogger("jarvis.llm.provider")


def _model_name():
    """Model from settings, falling back to the configured default."""

    try:
        from conversation.identity import identity

        model = str(identity.settings().get("model", "") or "").strip()

        if model:
            return model

    except Exception:
        pass

    try:
        from core.config import CHAT_MODEL

        return CHAT_MODEL

    except Exception:
        return "qwen3:4b"


class LLMProvider:

    def __init__(self, model=""):

        self.model = model or _model_name()

    def _client(self):
        """Import ollama on first use so the module stays importable."""

        import ollama

        return ollama

    def ask(self, prompt, options=None):
        """Send one prompt to the model and return its text."""

        try:

            client = self._client()

            response = client.chat(

                model=self.model,

                messages=[

                    {

                        "role": "user",

                        "content": prompt

                    }

                ],

                options=dict(options or {})

            )

            return response["message"]["content"]

        except Exception as error:

            log.warning("llm provider failed: %s", error)

            return str(error)

    def generate(self, prompt, options=None):
        """Alias kept so this provider matches OllamaProvider."""

        return self.ask(prompt, options)


llm = LLMProvider()
