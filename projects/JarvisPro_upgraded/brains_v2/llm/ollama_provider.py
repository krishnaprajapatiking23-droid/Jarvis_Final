"""
==========================================
JARVIS PRO
Ollama provider
==========================================

ROOT CAUSE OF "Empty response received from Ollama."
--------------------------------------------------
``qwen3:4b`` is a *thinking* model.  It emits its reasoning first - either
in ``message.thinking`` or inside a ``<think> ... </think>`` block - and
only then the answer.  The variation layer sends a token budget per turn
(``conversation/style_controller.py`` -> ``num_predict`` of 60/140/380).
For longer, analytical prompts the reasoning consumed the whole budget, so
``message.content`` really was empty.  That is exactly why the failure hit
sentences such as "Summarize the important points we discussed..." while
short chat still worked.

Secondary defect: every failure mode - offline, timeout, transport error,
malformed payload, missing model, empty content - collapsed into one
sentence, so nothing could be diagnosed, and the sentence was then handed
to the conversation layer, which decorated it ("As I mentioned, empty
response received from Ollama.").

WHAT THIS MODULE NOW DOES
-------------------------
* thinking is disabled for the normal call, and the answer budget can never
  be smaller than ``MIN_ANSWER_TOKENS``;
* if content is still empty, one retry runs *with* thinking and a large
  budget, and the answer is taken from the reasoning tail if needed;
* every failure returns a distinct sentence from ``STATUS_MESSAGES`` and
  records ``last_error`` plus a real log line for developers;
* both dict-style and pydantic-style Ollama responses are parsed.
"""

from brains_v2.llm.provider import LLMProvider, _model_name

import logging
import os
import re
import socket
import subprocess
import sys
import time

try:  # optional - only used for the diagnostic line below
    import httpx
except Exception:  # pragma: no cover - httpx missing is not fatal
    httpx = None

try:
    from ollama import Client
except ImportError:
    Client = None


log = logging.getLogger("jarvis.llm.ollama")

log.debug(
    "python=%s httpx=%s proxies=%s/%s",
    sys.executable,
    getattr(httpx, "__version__", "missing"),
    os.environ.get("HTTP_PROXY"),
    os.environ.get("HTTPS_PROXY"),
)

# One distinct sentence per failure mode.  The conversation layer treats
# every one of these as "the model was unavailable" and never decorates or
# stores them (see conversation/response_quality.py -> UNAVAILABLE).
STATUS_MESSAGES = {
    "offline": "I couldn't reach the language model, so I can't answer that right now.",
    "model_missing": "The language model is not installed, so I can't answer that yet.",
    "timeout": "The model took too long to answer, so I stopped waiting.",
    "transport": "The language model failed mid-request, so I have no answer for that.",
    "malformed": "The model returned something I couldn't read, so I have no answer.",
    "empty": "The model returned an empty answer, so I have nothing reliable to say.",
    "error": "The language model failed, so I can't answer that right now.",
}

# A thinking model needs room for the answer after its reasoning.
MIN_ANSWER_TOKENS = 256

# Reasoning that arrives inline instead of in message.thinking.
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
OPEN_THINK = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)


def _classify(error: BaseException) -> str:
    """Map an exception onto a STATUS_MESSAGES key."""

    text = f"{type(error).__name__}: {error}".lower()

    if "timeout" in text or "timed out" in text:
        return "timeout"

    if "not found" in text or "no such model" in text or "pull the model" in text:
        return "model_missing"

    if any(
        word in text
        for word in ("connect", "connection", "refused", "unreachable", "socket")
    ):
        return "offline"

    if any(word in text for word in ("read", "protocol", "remote", "transport", "stream")):
        return "transport"

    return "error"


def _clean(text: str) -> str:
    """Return only the user-visible part of the model content.

    The rules live in ``conversation.output_sanitizer`` so the
    provider, the variation layer, the dialogue manager and the
    TTS path all agree on what the user may see.
    """

    try:
        from conversation.output_sanitizer import sanitize

        return sanitize(text)

    except Exception:  # pragma: no cover - defensive
        body = text or ""
        body = THINK_BLOCK.sub(" ", body)
        body = OPEN_THINK.sub(" ", body)

        return body.strip()


def _internal(text: str) -> bool:
    """True when ``text`` still reads as reasoning or prompt echo."""

    try:
        from conversation.output_sanitizer import looks_internal

        return looks_internal(text or "")

    except Exception:  # pragma: no cover - defensive
        return False


def _answer_from_reasoning(thinking: str) -> str:
    """Last usable paragraph of the reasoning, used as a last resort."""

    blocks = [part.strip() for part in re.split(r"\n\s*\n", thinking or "") if part.strip()]

    if not blocks:
        return ""

    tail = blocks[-1]

    return tail if len(tail) > 30 else ""


DEFAULT_HOST = "http://127.0.0.1:11434"


def _split_host(host: str):
    """``http://127.0.0.1:11434`` -> ``("127.0.0.1", 11434)``."""
    text = (host or DEFAULT_HOST).split("//")[-1].strip("/")
    name, _, port = text.partition(":")

    try:
        number = int(port or 11434)
    except ValueError:
        number = 11434

    return name or "127.0.0.1", number


def _server_listening(host: str = DEFAULT_HOST, timeout: float = 0.4) -> bool:
    """True when something already serves the Ollama port.

    This is what tells "Ollama is not running" apart from "Ollama runs but
    the client call failed".  Without it, JARVIS launched a second
    ``ollama serve`` that could only fail with a port-bind error.
    """
    name, port = _split_host(host)

    try:
        with socket.create_connection((name, port), timeout=timeout):
            return True
    except OSError:
        return False


from brains_v2.llm.provider_state import (
    ProviderState,
    ProviderStateMachine,
)


class OllamaProvider(LLMProvider):

    name = "Ollama"

    model = "qwen3:4b"

    host = "http://127.0.0.1:11434"

    # Last technical reason, for developers and tests.
    last_error = ""

    # Set to False when the installed client rejects the think parameter.
    supports_think = True

    # None = not checked yet, True/False = the model is/ isn't installed.
    _model_ok = None

    @property
    def state(self) -> ProviderStateMachine:
        """Availability state machine (lazily created)."""
        machine = self.__dict__.get("_state")
        if machine is None:
            machine = ProviderStateMachine()
            self.__dict__["_state"] = machine
        return machine

    def status(self) -> dict:
        """Report availability without touching the network."""
        report = dict(self.state.report())
        report["model"] = getattr(self, "model", "")
        report["host"] = getattr(self, "host", "")
        report["client"] = bool(getattr(self, "client", None))
        return report

    def retry_now(self) -> None:
        """Explicit operator retry: clear the cooldown."""
        self.state.retry_now()

    def __init__(self, model=""):

        self.client = None
        self.last_error = ""
        self._model_ok = None

        try:
            self.model = model or _model_name()

        except Exception:
            pass

        self.connect()

    # =================================================
    # START OLLAMA SERVER
    # =================================================

    def start_server(self) -> bool:

        if _server_listening(self.host):
            self.state.mark_available()
            # Ollama is already up - the Windows tray app starts it - so a
            # second "ollama serve" could only fail with:
            #   bind: Only one usage of each socket address ...
            log.debug("ollama already listening on %s", self.host)

            return True

        if not self.state.should_attempt_start():
            log.debug(
                "skipping ollama start (state=%s, retry in %.0fs)",
                self.state.state,
                self.state.cooldown_remaining(),
            )

            return False

        self.state.mark_starting()

        try:
            log.info("starting ollama server")

            creation_flags = 0

            if os.name == "nt":
                creation_flags = subprocess.CREATE_NO_WINDOW

            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )

            time.sleep(2)

            if _server_listening(self.host):
                self.state.mark_available()
            else:
                self.state.mark_launched()

            return True

        except Exception as error:
            self.last_error = f"server start failed: {error!r}"
            delay = self.state.mark_failed(self.last_error)
            log.warning("%s (next attempt in %.0fs)", self.last_error, delay)

            return False

    # =================================================
    # CONNECT
    # =================================================

    def connect(self) -> bool:

        if Client is None:
            self.last_error = "ollama python package not installed"
            self.state.mark_unavailable(self.last_error)
            log.debug(self.last_error)

            return False

        for attempt in range(2):

            try:
                self.client = Client(host=self.host)
                self.client.list()

                log.info("ollama connected (model=%s)", self.model)
                self.state.mark_available()
                self.last_error = ""
                self._model_ok = None

                return True

            except Exception as error:
                self.client = None
                self.last_error = f"connection attempt {attempt + 1} failed: {error!r}"
                # Debug, not warning: a first miss is normal while the
                # service is still coming up, and the console belongs to
                # the user.  The final failure is still logged as an error.
                log.debug(self.last_error)

                if attempt == 0:
                    if _server_listening(self.host):
                        # The port answers, so the service is fine and the
                        # problem is the client call - retry, don't serve.
                        continue

                    self.start_server()
                    time.sleep(2)

        delay = self.state.mark_failed(self.last_error)
        log.warning(
            "ollama connection failed: %s (next attempt in %.0fs)",
            self.last_error,
            delay,
        )

        return False

    # =================================================
    # CHECK AVAILABILITY
    # =================================================

    def available(self) -> bool:

        if self.client is None:
            return self.connect()

        try:
            self.client.list()

            return True

        except Exception as error:
            self.last_error = f"connection lost: {error!r}"
            log.warning(self.last_error)
            self.client = None

            return self.connect()

    # =================================================
    # INSTALLED MODELS
    # =================================================

    def installed_models(self):
        """Names of the pulled models, or [] when that cannot be read."""

        if self.client is None:
            return []

        try:
            payload = self.client.list()

        except Exception as error:
            self.last_error = f"model list failed: {error!r}"
            log.debug(self.last_error)

            return []

        if isinstance(payload, dict):
            entries = payload.get("models")
        else:
            entries = getattr(payload, "models", None)

        names = []

        for entry in entries or []:
            if isinstance(entry, dict):
                name = entry.get("model") or entry.get("name") or ""
            else:
                name = getattr(entry, "model", "") or getattr(entry, "name", "")

            if name:
                names.append(str(name))

        return names

    def has_model(self, name: str = "") -> bool:
        """True when the wanted model is installed.

        When the list cannot be read this returns True: an unreadable list
        is not evidence of a missing model, and blocking the call would
        turn a reporting problem into a broken assistant.
        """

        wanted = (name or self.model or "").strip()

        if not wanted:
            return False

        installed = self.installed_models()

        if not installed:
            return True

        if wanted in installed:
            return True

        base = wanted.split(":")[0]

        return any(item.split(":")[0] == base for item in installed)

    def _model_ready(self) -> bool:
        """Cached has_model, so one list call serves the whole session."""

        if self._model_ok is None:
            self._model_ok = self.has_model()

        return bool(self._model_ok)

    # =================================================
    # LOW LEVEL CHAT
    # =================================================

    def _chat(self, prompt, options, think):
        """One chat call -> ``(content, thinking)``.

        Handles both dict responses and the newer pydantic objects, so the
        answer is never lost to a parsing mismatch.
        """

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "options": dict(options or {}),
        }

        if think is not None and self.supports_think:
            kwargs["think"] = think

        try:
            response = self.client.chat(**kwargs)

        except TypeError as error:
            if "think" not in str(error).lower():
                raise

            # Older client without thinking support.
            self.supports_think = False
            kwargs.pop("think", None)
            response = self.client.chat(**kwargs)

        if response is None:
            return "", ""

        message = None

        if isinstance(response, dict):
            message = response.get("message")
        else:
            message = getattr(response, "message", None)

        if message is None:
            return "", ""

        if isinstance(message, dict):
            content = message.get("content") or ""
            thinking = message.get("thinking") or message.get("reasoning") or ""
        else:
            content = getattr(message, "content", "") or ""
            thinking = (
                getattr(message, "thinking", "")
                or getattr(message, "reasoning", "")
                or ""
            )

        return str(content), str(thinking)

    # =================================================
    # GENERATE
    # =================================================

    def generate(self, prompt, options=None):
        """Ask the model, optionally with generation parameters.

        ``options`` carries temperature / top_p / repeat_penalty /
        num_predict / seed, chosen per turn by
        ``conversation/style_controller.py``.

        Returns the answer text, or one of ``STATUS_MESSAGES`` when the
        model genuinely produced nothing.  ``self.last_error`` always holds
        the technical reason.
        """

        text = (prompt or "").strip()

        if not text:
            self.last_error = "empty prompt (prompt construction failure)"
            log.warning(self.last_error)

            return STATUS_MESSAGES["malformed"]

        if not self.available():
            return STATUS_MESSAGES[
                "model_missing" if Client is None else "offline"
            ]

        if not self._model_ready():
            self.last_error = (
                f"model {self.model!r} is not installed "
                f"(run: ollama pull {self.model})"
            )
            log.warning(self.last_error)

            return STATUS_MESSAGES["model_missing"]

        settings = dict(options or {})

        # Reserve room for the answer itself; reasoning must not eat it.
        budget = int(settings.get("num_predict") or 0)
        settings["num_predict"] = max(budget, MIN_ANSWER_TOKENS)

        attempts = (
            # 1. no reasoning at all - fastest and usually enough
            (False, settings),
            # 2. reasoning allowed, with a budget that fits both parts
            (True, {**settings, "num_predict": max(settings["num_predict"], 1024)}),
        )

        thinking_seen = ""

        for think, call_options in attempts:

            try:
                content, thinking = self._chat(text, call_options, think)

            except Exception as error:
                reason = _classify(error)
                self.last_error = f"{reason}: {type(error).__name__}: {error}"
                log.warning("ollama call failed (%s)", self.last_error)

                if reason in ("transport", "error"):
                    self.client = None

                    if self.connect():
                        continue

                return STATUS_MESSAGES[reason]

            thinking_seen = thinking or thinking_seen
            answer = _clean(content)

            if answer:
                self.last_error = ""

                return answer

            self.last_error = (
                "empty content "
                f"(think={think}, num_predict={call_options.get('num_predict')}, "
                f"reasoning_chars={len(thinking or '')})"
            )
            log.warning("ollama returned no content: %s", self.last_error)

        # Last resort: the model reasoned but never wrote the answer out.
        # The reasoning tail may only be used when it is a clean sentence.
        # Handing back the scratchpad is what produced replies such as
        # "We are in the middle of conversation about Python (the topic).
        # The user has just asked ...".
        recovered = _clean(_answer_from_reasoning(thinking_seen))

        if recovered and not _internal(recovered):
            log.info("recovered answer from model reasoning")

            return recovered

        if recovered:
            log.warning("discarded internal reasoning instead of answering")

        return STATUS_MESSAGES["empty"]


__all__ = [
    "OllamaProvider",
    "STATUS_MESSAGES",
    "MIN_ANSWER_TOKENS",
    "DEFAULT_HOST",
    "_server_listening",
]
