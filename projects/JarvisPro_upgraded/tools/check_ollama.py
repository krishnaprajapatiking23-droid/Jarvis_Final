"""
==========================================
JARVIS PRO
Ollama service check
==========================================

Run this whenever JARVIS says it cannot reach the language model, or when
``ollama serve`` prints::

    Error: listen tcp 127.0.0.1:11434: bind: Only one usage of each socket
    address (protocol/network address/port) is normally permitted.

That message is not a JARVIS fault and not a broken install - it means
Ollama is ALREADY running (the Windows tray app starts it at login), which
is exactly what JARVIS needs.  Starting it a second time can never work.

This tool answers the three questions that matter, with no guessing:

    * is the service listening on the port?
    * can the python client talk to it?
    * is the model from config/settings.json actually pulled?

Usage::

    python tools\\check_ollama.py

Exit code 0 means JARVIS can use the model.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _configured_model() -> str:
    """The model name from settings, or "" when it cannot be read."""

    try:
        from brains_v2.llm.provider import _model_name

        return (_model_name() or "").strip()

    except Exception:
        return ""


def probe(host: str = "", model: str = "", listening=None, provider=None) -> dict:
    """Inspect the local Ollama service.

    ``listening`` and ``provider`` exist so the tests can drive this
    without a real server; normal runs pass neither.
    """

    from brains_v2.llm import ollama_provider as backend

    target = host or backend.DEFAULT_HOST
    wanted = model or _configured_model() or backend.OllamaProvider.model

    state = {
        "host": target,
        "model": wanted,
        "running": False,
        "client": False,
        "models": [],
        "model_installed": False,
        "error": "",
    }

    if listening is None:
        state["running"] = backend._server_listening(target)
    else:
        state["running"] = bool(listening)

    if provider is None and state["running"]:
        try:
            provider = backend.OllamaProvider(model=wanted)

        except Exception as error:
            state["error"] = f"{type(error).__name__}: {error}"

    if provider is not None:
        state["client"] = provider.client is not None
        state["models"] = list(provider.installed_models())
        state["model_installed"] = bool(state["client"]) and provider.has_model(wanted)
        state["error"] = state["error"] or getattr(provider, "last_error", "")

    return state


def is_ready(state: dict) -> bool:
    return bool(state["running"] and state["client"] and state["model_installed"])


def describe(state: dict) -> list:
    """Plain-language report lines for the state returned by ``probe``."""

    lines = [
        f"host           : {state['host']}",
        "service        : " + ("running" if state["running"] else "NOT running"),
        "python client  : " + ("connected" if state["client"] else "not connected"),
        f"model wanted   : {state['model']}",
        "models present : " + (", ".join(state["models"]) or "(none reported)"),
    ]

    if is_ready(state):
        lines.append("result         : OK - JARVIS can use the model")
        lines.append("")
        lines.append("Do not run 'ollama serve' again - it is already running.")
        lines.append("Just start JARVIS:  python main.py")

        return lines

    lines.append("result         : problem found")
    lines.append("")

    if not state["running"]:
        lines.append("Ollama is not running. Open the Ollama app from the Start")
        lines.append("menu, or run this in a separate window:  ollama serve")

    elif not state["client"]:
        lines.append("The port answers, so the service is up, but the python")
        lines.append("client cannot talk to it. Repair the client:")
        lines.append("    python -m pip install -U ollama")

    elif not state["model_installed"]:
        lines.append("The service is up but the model is missing. Pull it:")
        lines.append(f"    ollama pull {state['model']}")

    if state["error"]:
        lines.append("")
        lines.append(f"technical detail: {state['error']}")

    return lines


def main() -> int:
    state = probe()

    print("=" * 68)
    print("JARVIS PRO - Ollama check")
    print("=" * 68)

    for line in describe(state):
        print(line)

    print("=" * 68)

    return 0 if is_ready(state) else 1


if __name__ == "__main__":
    sys.exit(main())
