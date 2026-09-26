"""
==========================================
JARVIS PRO
Advanced model system - routing, fallback, health
==========================================

Roadmap section 35.

What this adds on top of the existing ``brains_v2.llm`` stack:

  * a capability registry (chat / coding / research / vision / fast)
    so callers ask for a *capability*, never a model name;
  * ordered fallback: local Ollama first (offline-first rule), then any
    cloud provider the user actually configured;
  * per-model health, latency and success tracking, with rate-limit
    cool-down - the routing idea taken from Mark-XXXIX-OR ``or_client.py``
    and Mark-LII ``core/llm_client.py``, rebuilt on JARVIS's own provider;
  * every call is timed into ``core.observability``.

No credential is required: with no API keys at all the router uses the
existing local Ollama provider only.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from config import config
from core.observability import observability


RATE_LIMIT_COOLDOWN = 60.0
FAILURE_COOLDOWN = 30.0


@dataclass
class ModelRecord:
    """One routable model and everything known about how well it works."""

    name: str
    provider: str
    capabilities: tuple[str, ...]
    local: bool = True
    weight: int = 50
    runs: int = 0
    failures: int = 0
    total_latency: float = 0.0
    blocked_until: float = 0.0
    last_error: str = ""

    @property
    def avg_latency(self) -> float:
        return round(self.total_latency / self.runs, 3) if self.runs else 0.0

    @property
    def success_rate(self) -> float:
        if not self.runs:
            return 1.0

        return round((self.runs - self.failures) / self.runs, 3)

    def available(self) -> bool:
        return time.time() >= self.blocked_until

    def report(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "provider": self.provider,
            "local": self.local,
            "capabilities": list(self.capabilities),
            "runs": self.runs,
            "failures": self.failures,
            "success_rate": self.success_rate,
            "avg_latency": self.avg_latency,
            "available": self.available(),
            "last_error": self.last_error,
        }


class ModelRouter:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._models: list[ModelRecord] = []
        self._providers: dict[str, Callable[..., str]] = {}
        self._selection_history: list[dict[str, Any]] = []
        self._built = False

    # ---------------------------------------------------- registry

    def _build(self) -> None:
        if self._built:
            return

        with self._lock:
            if self._built:
                return

            chat = str(config.get("model.chat", "qwen3:4b"))
            vision = str(config.get("model.vision", "gemma3:12b"))
            coding = str(config.get("model.coding", "") or chat)

            models = [
                ModelRecord(chat, "ollama", ("chat", "research", "fast"), True, 100),
                ModelRecord(coding, "ollama", ("coding",), True, 95),
                ModelRecord(vision, "ollama", ("vision",), True, 90),
            ]

            if config.has("openrouter"):
                models += [
                    ModelRecord(
                        "meta-llama/llama-3.3-70b-instruct:free",
                        "openrouter",
                        ("chat", "research"),
                        False,
                        60,
                    ),
                    ModelRecord(
                        "qwen/qwen3-coder:free",
                        "openrouter",
                        ("coding",),
                        False,
                        60,
                    ),
                ]

            if config.has("groq"):
                models.append(
                    ModelRecord(
                        "llama-3.3-70b-versatile",
                        "groq",
                        ("chat", "fast", "research"),
                        False,
                        55,
                    )
                )

            if config.has("gemini"):
                models += [
                    ModelRecord(
                        "gemini-2.5-flash",
                        "gemini",
                        ("chat", "research", "fast"),
                        False,
                        50,
                    ),
                    ModelRecord(
                        "gemini-2.5-flash",
                        "gemini",
                        ("vision",),
                        False,
                        50,
                    ),
                ]

            # de-duplicate identical (provider, model, capability set)
            seen: set[tuple[str, str, tuple[str, ...]]] = set()
            unique: list[ModelRecord] = []

            for record in models:
                token = (record.provider, record.name, record.capabilities)

                if token in seen or not record.name:
                    continue

                seen.add(token)
                unique.append(record)

            self._models = unique
            self._built = True

    def refresh(self) -> None:
        """Rebuild after the user adds a key or changes models."""

        with self._lock:
            self._built = False
            self._models = []

        config.reload()
        self._build()

    def models(self) -> list[dict[str, Any]]:
        self._build()

        return [record.report() for record in self._models]

    def candidates(self, capability: str = "chat") -> list[ModelRecord]:
        """Models that can serve a capability, best first."""

        self._build()

        offline_first = bool(config.get("model.offline_first", True))
        allow_cloud = bool(config.get("model.allow_cloud", True))

        pool = [
            record
            for record in self._models
            if capability in record.capabilities
            and (record.local or allow_cloud)
            and record.available()
        ]

        def rank(record: ModelRecord) -> tuple:
            return (
                0 if (record.local and offline_first) else 1,
                -record.success_rate,
                -record.weight / 100.0,
                record.avg_latency,
            )

        return sorted(pool, key=rank)

    # ---------------------------------------------------- providers

    def _provider(self, name: str) -> Callable[..., str]:
        """Lazily build a callable ``(model, prompt, options) -> text``."""

        if name in self._providers:
            return self._providers[name]

        if name == "ollama":
            call = self._call_ollama

        elif name == "openrouter":
            call = self._call_openrouter

        elif name == "groq":
            call = self._call_openai_compatible_groq

        elif name == "gemini":
            call = self._call_gemini

        else:
            raise RuntimeError(f"unknown provider: {name}")

        self._providers[name] = call

        return call

    def _call_ollama(self, model: str, prompt: str, options: dict) -> str:
        """Reuse the project's existing, already-hardened Ollama provider."""

        from brains_v2.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider(model=model)

        text = provider.ask(prompt, options=options)

        if not str(text or "").strip():
            raise RuntimeError(provider.last_error or "empty response")

        return str(text)

    def _http_json(
        self,
        url: str,
        payload: dict,
        headers: dict,
        timeout: float,
    ) -> dict:
        """POST JSON with urllib so no new dependency is introduced."""

        import urllib.error
        import urllib.request

        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url, data=body, method="POST")

        for key, value in headers.items():
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "ignore"))

        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "ignore")[:300]

            if error.code in (429, 402):
                raise RuntimeError(f"rate_limited: {detail}") from error

            raise RuntimeError(f"http {error.code}: {detail}") from error

    def _chat_completions(
        self,
        url: str,
        key: str,
        model: str,
        prompt: str,
        options: dict,
        extra_headers: dict | None = None,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        headers.update(extra_headers or {})

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(options.get("temperature", 0.7)),
            "max_tokens": int(options.get("num_predict", 1024)),
        }

        data = self._http_json(
            url,
            payload,
            headers,
            float(config.get("model.timeout", 120)),
        )

        choices = data.get("choices") or []

        if not choices:
            raise RuntimeError("empty response")

        return str(choices[0].get("message", {}).get("content", "")).strip()

    def _call_openrouter(self, model: str, prompt: str, options: dict) -> str:
        return self._chat_completions(
            "https://openrouter.ai/api/v1/chat/completions",
            config.api_key("openrouter"),
            model,
            prompt,
            options,
            {"X-Title": "JARVIS PRO"},
        )

    def _call_openai_compatible_groq(
        self,
        model: str,
        prompt: str,
        options: dict,
    ) -> str:
        return self._chat_completions(
            "https://api.groq.com/openai/v1/chat/completions",
            config.api_key("groq"),
            model,
            prompt,
            options,
        )

    def _call_gemini(self, model: str, prompt: str, options: dict) -> str:
        key = config.api_key("gemini")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(options.get("temperature", 0.7)),
                "maxOutputTokens": int(options.get("num_predict", 1024)),
            },
        }

        data = self._http_json(
            url,
            payload,
            {"Content-Type": "application/json"},
            float(config.get("model.timeout", 120)),
        )

        candidates = data.get("candidates") or []

        if not candidates:
            raise RuntimeError("empty response")

        parts = candidates[0].get("content", {}).get("parts", [])

        return "".join(str(part.get("text", "")) for part in parts).strip()

    # ---------------------------------------------------- asking

    def ask(
        self,
        prompt: str,
        capability: str = "chat",
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Run a prompt through the best available model, with fallback.

        Returns ``{"text", "model", "provider", "latency", "attempts", "ok"}``
        so callers can record which model answered (selection history).
        """

        options = dict(options or {})
        attempts: list[dict[str, Any]] = []

        for record in self.candidates(capability):
            started = time.time()

            try:
                text = self._provider(record.provider)(
                    record.name,
                    prompt,
                    options,
                )

                latency = time.time() - started

                with self._lock:
                    record.runs += 1
                    record.total_latency += latency
                    record.last_error = ""

                observability.record(
                    f"model.{record.provider}",
                    latency,
                    ok=True,
                    model=record.name,
                    capability=capability,
                )

                result = {
                    "ok": True,
                    "text": text,
                    "model": record.name,
                    "provider": record.provider,
                    "latency": round(latency, 3),
                    "attempts": attempts,
                }

                self._remember(capability, result)

                return result

            except Exception as error:
                latency = time.time() - started
                message = f"{type(error).__name__}: {error}"

                with self._lock:
                    record.runs += 1
                    record.failures += 1
                    record.total_latency += latency
                    record.last_error = message[:300]
                    record.blocked_until = time.time() + (
                        RATE_LIMIT_COOLDOWN
                        if "rate_limited" in message
                        else FAILURE_COOLDOWN
                    )

                observability.record(
                    f"model.{record.provider}",
                    latency,
                    ok=False,
                    error=message,
                    model=record.name,
                    capability=capability,
                )

                attempts.append(
                    {
                        "model": record.name,
                        "provider": record.provider,
                        "error": message[:200],
                    }
                )

        observability.warn(
            "model_router",
            "no model could answer",
            capability=capability,
            attempts=attempts,
        )

        return {
            "ok": False,
            "text": "",
            "model": "",
            "provider": "",
            "latency": 0.0,
            "attempts": attempts,
        }

    def text(
        self,
        prompt: str,
        capability: str = "chat",
        options: dict | None = None,
        default: str = "",
    ) -> str:
        """Convenience wrapper for callers that only want the answer."""

        result = self.ask(prompt, capability, options)

        return result["text"] if result["ok"] else default

    def json(
        self,
        prompt: str,
        capability: str = "chat",
        options: dict | None = None,
    ) -> Any:
        """Ask for JSON and parse it, tolerating markdown fences."""

        raw = self.text(prompt, capability, options)

        if not raw:
            return None

        cleaned = raw.strip()

        if "```" in cleaned:
            blocks = cleaned.split("```")

            for block in blocks:
                candidate = block.strip()

                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()

                if candidate.startswith(("{", "[")):
                    cleaned = candidate
                    break

        start = min(
            [index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0]
            or [-1]
        )

        if start > 0:
            cleaned = cleaned[start:]

        end = max(cleaned.rfind("}"), cleaned.rfind("]"))

        if end >= 0:
            cleaned = cleaned[: end + 1]

        try:
            return json.loads(cleaned)

        except Exception:
            return None

    # ---------------------------------------------------- diagnostics

    def _remember(self, capability: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._selection_history.append(
                {
                    "at": time.time(),
                    "capability": capability,
                    "model": result["model"],
                    "provider": result["provider"],
                    "latency": result["latency"],
                    "fallbacks": len(result["attempts"]),
                }
            )

            del self._selection_history[:-200]

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._selection_history[-limit:])

    def health(self) -> dict[str, Any]:
        """Model health check for startup diagnostics and the dashboard."""

        self._build()

        return {
            "offline_first": bool(config.get("model.offline_first", True)),
            "cloud_allowed": bool(config.get("model.allow_cloud", True)),
            "models": self.models(),
            "capabilities": sorted(
                {
                    capability
                    for record in self._models
                    for capability in record.capabilities
                }
            ),
            "services": config.status(),
        }


router = ModelRouter()
