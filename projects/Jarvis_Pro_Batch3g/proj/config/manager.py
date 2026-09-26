"""
==========================================
JARVIS PRO
Centralized configuration & API manager
==========================================

ONE place that knows about settings, secrets and endpoints.

Resolution order for any key (first hit wins):

    1. environment variable            JARVIS_VOICE_ENABLED / GEMINI_API_KEY
    2. .env file next to the project   (parsed without python-dotenv)
    3. config/api_keys.json            (secrets + service settings, gitignored)
    4. config/settings.json            (existing JARVIS settings file)
    5. core/config.py constants        (legacy defaults, read-only)
    6. the default passed by caller

Design rules (from the integration brief):
  * no secret is ever hard-coded or invented here;
  * a missing key is never fatal - callers ask ``has()`` / ``api_key()``
    and degrade gracefully;
  * every value is reachable with a dotted path, so a new feature needs
    zero edits in other files;
  * writes are atomic and thread-safe.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- paths


def base_dir() -> Path:
    """Project root, also correct inside a PyInstaller bundle."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).resolve().parent.parent


BASE_DIR = base_dir()
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
SECRETS_FILE = CONFIG_DIR / "api_keys.json"
ENV_FILE = BASE_DIR / ".env"


# ---------------------------------------------------------------- services
#
# Every external service JARVIS can use. ``key`` is the name inside
# api_keys.json, ``env`` the environment variable, ``local`` marks services
# that need no credential at all (preferred - see rule 5 of the brief).

SERVICES: dict[str, dict[str, Any]] = {
    "ollama": {
        "env": "OLLAMA_HOST",
        "key": "ollama_host",
        "default": "http://127.0.0.1:11434",
        "local": True,
        "purpose": "local chat / vision models (primary brain)",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "key": "gemini_api_key",
        "local": False,
        "purpose": "optional cloud fallback, live voice, vision",
    },
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "key": "openrouter_api_key",
        "local": False,
        "purpose": "optional free-tier multi-model routing",
    },
    "groq": {
        "env": "GROQ_API_KEY",
        "key": "groq_api_key",
        "local": False,
        "purpose": "optional fast cloud fallback",
    },
    "openweather": {
        "env": "OPENWEATHER_API_KEY",
        "key": "openweather_api_key",
        "local": False,
        "purpose": "optional weather data (wttr.in used when absent)",
    },
}


DEFAULTS: dict[str, Any] = {
    "assistant.name": "Jarvis",
    "assistant.owner": "",
    "assistant.language": "en",
    "voice.enabled": True,
    "voice.input_device": "",
    "voice.output_device": "",
    "voice.wake_words": ["jarvis", "hey jarvis", "wake up jarvis"],
    "model.chat": "qwen3:4b",
    "model.vision": "gemma3:12b",
    "model.coding": "",
    "model.offline_first": True,
    "model.allow_cloud": True,
    "model.timeout": 120,
    "agent.max_steps": 8,
    "agent.max_retries": 2,
    "agent.confirm_risky": True,
    "agent.max_concurrent": 1,
    "policy.mode": "ask",
    "monitor.cpu": 90.0,
    "monitor.ram": 90.0,
    "monitor.temp": 85.0,
    "monitor.gpu": 95.0,
    "backup.keep": 10,
    "undo.keep": 200,
    "debug": False,
}


# ---------------------------------------------------------------- helpers


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser - no third-party dependency needed."""

    values: dict[str, str] = {}

    if not path.exists():
        return values

    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()

            if not line or line.startswith(("#", ";")):
                continue

            if line.lower().startswith("export "):
                line = line[7:]

            name, sep, value = line.partition("=")

            if not sep:
                continue

            value = value.strip().strip('"').strip("'")
            values[name.strip()] = value

    except Exception:
        return values

    return values


def _env_name(path: str) -> str:
    """``voice.enabled`` -> ``JARVIS_VOICE_ENABLED``."""

    return "JARVIS_" + path.replace(".", "_").upper()


def _coerce(value: Any, like: Any) -> Any:
    """Make a string from env/.env look like the default it overrides."""

    if not isinstance(value, str) or like is None:
        return value

    if isinstance(like, bool):
        return value.strip().lower() in ("1", "true", "yes", "on")

    if isinstance(like, int) and not isinstance(like, bool):
        try:
            return int(float(value))
        except ValueError:
            return like

    if isinstance(like, float):
        try:
            return float(value)
        except ValueError:
            return like

    if isinstance(like, list):
        return [part.strip() for part in value.split(",") if part.strip()]

    return value


def _dig(tree: Any, path: str) -> tuple[bool, Any]:
    """Walk a dotted path through nested dicts. Also accepts flat keys."""

    if not isinstance(tree, dict):
        return False, None

    if path in tree:
        return True, tree[path]

    node: Any = tree

    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None

        node = node[part]

    return True, node


def _legacy() -> dict[str, Any]:
    """Values from the original ``core/config.py`` so nothing regresses."""

    try:
        from core import config as legacy

    except Exception:
        return {}

    return {
        "assistant.name": getattr(legacy, "ASSISTANT_NAME", None),
        "assistant.owner": getattr(legacy, "OWNER_NAME", None),
        "assistant.language": getattr(legacy, "DEFAULT_LANGUAGE", None),
        "model.chat": getattr(legacy, "CHAT_MODEL", None),
        "model.vision": getattr(legacy, "VISION_MODEL", None),
        "voice.enabled": getattr(legacy, "VOICE_ENABLED", None),
        "debug": getattr(legacy, "DEBUG_MODE", None),
        "version": getattr(legacy, "VERSION", None),
    }


# ---------------------------------------------------------------- manager


class ConfigManager:
    """Thread-safe, cached, write-through configuration store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: dict[str, Any] | None = None
        self._secrets: dict[str, Any] | None = None
        self._dotenv: dict[str, str] | None = None
        self._legacy: dict[str, Any] | None = None

    # ---------------------------------------------------- loading

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))

                if isinstance(data, dict):
                    return data

        except Exception:
            pass

        return {}

    def settings(self) -> dict[str, Any]:
        with self._lock:
            if self._settings is None:
                self._settings = self._read_json(SETTINGS_FILE)

            return self._settings

    def secrets(self) -> dict[str, Any]:
        with self._lock:
            if self._secrets is None:
                self._secrets = self._read_json(SECRETS_FILE)

            return self._secrets

    def dotenv(self) -> dict[str, str]:
        with self._lock:
            if self._dotenv is None:
                self._dotenv = _parse_env_file(ENV_FILE)

            return self._dotenv

    def legacy(self) -> dict[str, Any]:
        with self._lock:
            if self._legacy is None:
                self._legacy = {
                    name: value
                    for name, value in _legacy().items()
                    if value is not None
                }

            return self._legacy

    def reload(self) -> None:
        """Drop every cache - used by the settings UI and by tests."""

        with self._lock:
            self._settings = None
            self._secrets = None
            self._dotenv = None
            self._legacy = None

    # ---------------------------------------------------- reading

    def get(self, path: str, default: Any = None) -> Any:
        """Resolve one dotted setting through every configured source."""

        fallback = DEFAULTS.get(path, default)

        name = _env_name(path)

        raw = os.environ.get(name)

        if raw is None:
            raw = self.dotenv().get(name)

        if raw is not None:
            return _coerce(raw, fallback)

        for source in (self.secrets(), self.settings()):
            found, value = _dig(source, path)

            if found and value not in (None, ""):
                return value

        if path in self.legacy():
            return self.legacy()[path]

        if fallback is None and default is not None:
            return default

        return fallback

    def all(self) -> dict[str, Any]:
        """Every known setting with its resolved value (secrets excluded)."""

        names = set(DEFAULTS) | set(self.legacy())

        return {name: self.get(name) for name in sorted(names)}

    # ---------------------------------------------------- writing

    def set(self, path: str, value: Any) -> None:
        """Persist one setting into ``config/settings.json`` atomically."""

        with self._lock:
            data = dict(self.settings())

            node = data
            parts = path.split(".")

            for part in parts[:-1]:
                child = node.get(part)

                if not isinstance(child, dict):
                    child = {}
                    node[part] = child

                node = child

            node[parts[-1]] = value

            self._write(SETTINGS_FILE, data)
            self._settings = data

    def set_api_key(self, service: str, value: str) -> None:
        """Store a credential in ``config/api_keys.json`` (never in source)."""

        service = service.strip().lower()
        spec = SERVICES.get(service, {})
        key = str(spec.get("key") or f"{service}_api_key")

        with self._lock:
            data = dict(self.secrets())
            data[key] = (value or "").strip()

            self._write(SECRETS_FILE, data)
            self._secrets = data

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        temp.replace(path)

    # ---------------------------------------------------- services

    def api_key(self, service: str) -> str:
        """Credential for a service, or "" when the user has not supplied one."""

        service = service.strip().lower()
        spec = SERVICES.get(service)

        if not spec:
            spec = {"env": f"{service.upper()}_API_KEY", "key": f"{service}_api_key"}

        env_name = str(spec.get("env"))

        value = os.environ.get(env_name) or self.dotenv().get(env_name) or ""

        if not value:
            value = str(self.secrets().get(str(spec.get("key")), "") or "")

        if not value:
            value = str(spec.get("default", "") or "")

        return value.strip()

    def has(self, service: str) -> bool:
        """True when a service is usable right now."""

        spec = SERVICES.get(service.strip().lower(), {})

        if spec.get("local"):
            return True

        if not self.get("model.allow_cloud", True):
            return False

        return bool(self.api_key(service))

    def status(self) -> dict[str, dict[str, Any]]:
        """Service report for the dashboard / diagnostics - no secrets leak."""

        report: dict[str, dict[str, Any]] = {}

        for name, spec in SERVICES.items():
            key = self.api_key(name)

            report[name] = {
                "configured": bool(key) if not spec.get("local") else True,
                "local": bool(spec.get("local")),
                "purpose": spec.get("purpose", ""),
                "env": spec.get("env", ""),
                "hint": "" if key or spec.get("local") else (
                    f"add {spec.get('key')} to config/api_keys.json "
                    f"or set {spec.get('env')}"
                ),
            }

        return report

    def missing(self) -> list[str]:
        """Optional services the user could still enable."""

        return [
            name
            for name, spec in SERVICES.items()
            if not spec.get("local") and not self.api_key(name)
        ]

    # ---------------------------------------------------- paths

    def path(self, *parts: str) -> Path:
        """Project-relative path helper, so nothing hard-codes a directory."""

        return BASE_DIR.joinpath(*parts)

    def data_path(self, *parts: str) -> Path:
        folder = BASE_DIR / "data"
        folder.mkdir(parents=True, exist_ok=True)

        return folder.joinpath(*parts)


config = ConfigManager()
