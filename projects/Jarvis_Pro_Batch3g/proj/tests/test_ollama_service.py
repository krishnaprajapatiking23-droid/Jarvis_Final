"""
==========================================
JARVIS PRO
Ollama service handling
==========================================

These tests lock down the repair for the port-bind error:

    Error: listen tcp 127.0.0.1:11434: bind: Only one usage of each socket
    address (protocol/network address/port) is normally permitted.

JARVIS must never start a second server when one is already listening, must
not shout a warning at the user on a first failed attempt, and must say
plainly when the model itself is missing.  No real server is needed here.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from brains_v2.llm import ollama_provider as backend
from brains_v2.llm.ollama_provider import STATUS_MESSAGES, OllamaProvider
from tools import check_ollama


class FakeClient:
    """Stand-in for ollama.Client - no network, no package needed."""

    def __init__(self, models=("qwen3:4b",), list_fails=False):
        self.models = list(models)
        self.list_fails = list_fails
        self.chats = []

    def list(self):
        if self.list_fails:
            raise ConnectionError("Failed to connect to Ollama")

        return {"models": [{"model": name} for name in self.models]}

    def chat(self, **kwargs):
        self.chats.append(kwargs)

        return {"message": {"content": "Python is a programming language."}}


def make_provider(models=("qwen3:4b",), list_fails=False):
    """A provider with a fake client and no __init__ side effects."""

    provider = OllamaProvider.__new__(OllamaProvider)
    provider.client = FakeClient(models, list_fails)
    provider.model = "qwen3:4b"
    provider.host = backend.DEFAULT_HOST
    provider.last_error = ""
    provider.supports_think = True
    provider._model_ok = None

    return provider


class _Swap:
    """Temporarily replace module attributes."""

    def __init__(self, module, **values):
        self.module = module
        self.values = values
        self.saved = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = getattr(self.module, key)
            setattr(self.module, key, value)

        return self

    def __exit__(self, *_):
        for key, value in self.saved.items():
            setattr(self.module, key, value)

        return False


class _Popen:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)

        return self


# ======================================================================
# the port probe
# ======================================================================


def test_host_string_is_split_into_address_and_port():
    assert backend._split_host("http://127.0.0.1:11434") == ("127.0.0.1", 11434)
    assert backend._split_host("") == ("127.0.0.1", 11434)
    assert backend._split_host("http://localhost") == ("localhost", 11434)
    assert backend._split_host("http://127.0.0.1:bad") == ("127.0.0.1", 11434)


def test_closed_port_is_reported_as_not_listening():
    # Port 1 is never an Ollama server, so this must be False everywhere.
    assert backend._server_listening("http://127.0.0.1:1", timeout=0.2) is False


# ======================================================================
# never a second "ollama serve"
# ======================================================================


def test_second_server_is_not_started_when_the_port_is_busy():
    provider = make_provider()
    spawn = _Popen()

    with _Swap(backend, _server_listening=lambda *a, **k: True):
        with _Swap(backend.subprocess, Popen=spawn):
            assert provider.start_server() is True

    assert spawn.calls == [], "a second ollama serve was launched"


def test_server_is_started_when_nothing_is_listening():
    provider = make_provider()
    spawn = _Popen()

    with _Swap(backend, _server_listening=lambda *a, **k: False):
        with _Swap(backend.subprocess, Popen=spawn):
            with _Swap(backend.time, sleep=lambda *_: None):
                assert provider.start_server() is True

    assert spawn.calls == [["ollama", "serve"]]


def test_a_failed_call_on_a_live_port_does_not_spawn_a_server():
    provider = OllamaProvider.__new__(OllamaProvider)
    provider.client = None
    provider.model = "qwen3:4b"
    provider.host = backend.DEFAULT_HOST
    provider.last_error = ""
    provider._model_ok = None

    spawn = _Popen()

    def broken_client(host=""):
        raise ConnectionError("Failed to connect to Ollama")

    with _Swap(
        backend,
        Client=broken_client,
        _server_listening=lambda *a, **k: True,
    ):
        with _Swap(backend.subprocess, Popen=spawn):
            with _Swap(backend.time, sleep=lambda *_: None):
                assert provider.connect() is False

    assert spawn.calls == []
    assert "connection attempt" in provider.last_error


# ======================================================================
# the model itself
# ======================================================================


def test_installed_models_are_listed():
    provider = make_provider(models=("qwen3:4b", "llama3:8b"))

    assert provider.installed_models() == ["qwen3:4b", "llama3:8b"]
    assert provider.has_model("qwen3:4b") is True
    assert provider.has_model("llama3") is True
    assert provider.has_model("mistral") is False


def test_missing_model_is_named_with_the_pull_command():
    provider = make_provider(models=("llama3:8b",))

    reply = provider.generate("What is Python?")

    assert reply == STATUS_MESSAGES["model_missing"]
    assert "ollama pull qwen3:4b" in provider.last_error


def test_present_model_reaches_the_chat_call():
    provider = make_provider(models=("qwen3:4b",))

    reply = provider.generate("What is Python?")

    assert reply == "Python is a programming language."
    assert provider.client.chats, "the model was never called"
    assert provider.last_error == ""


def test_an_unreadable_model_list_does_not_block_the_answer():
    provider = make_provider(list_fails=True)

    # The list cannot be read, but that is not proof the model is missing.
    assert provider.has_model() is True


# ======================================================================
# the check tool
# ======================================================================


def test_check_tool_reports_a_healthy_service():
    state = check_ollama.probe(
        model="qwen3:4b",
        listening=True,
        provider=make_provider(),
    )

    assert check_ollama.is_ready(state) is True

    text = "\n".join(check_ollama.describe(state))

    assert "OK - JARVIS can use the model" in text
    assert "Do not run 'ollama serve' again" in text


def test_check_tool_explains_a_stopped_service():
    state = check_ollama.probe(model="qwen3:4b", listening=False, provider=None)

    assert check_ollama.is_ready(state) is False

    text = "\n".join(check_ollama.describe(state))

    assert "NOT running" in text
    assert "Ollama app" in text


def test_check_tool_explains_a_missing_model():
    state = check_ollama.probe(
        model="qwen3:4b",
        listening=True,
        provider=make_provider(models=("llama3:8b",)),
    )

    assert state["model_installed"] is False

    text = "\n".join(check_ollama.describe(state))

    assert "ollama pull qwen3:4b" in text
