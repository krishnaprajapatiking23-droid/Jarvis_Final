# Jarvis Pro final hardened setup

## Installation

1. Use Python 3.11 or newer in a virtual environment.
2. Install only the capabilities required: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`; never commit `.env` or `config/api_keys.json`.
4. Run `python main.py` for the authoritative BrainV2 voice/text pipeline.
5. Run tests with `python tools/run_tests.py` and `python -m unittest tests.test_final_hardening tests.test_remaining_features`.

## Architecture

`main.py → jarvis.Jarvis → brains_v2.voice.pipeline → BrainV2 → conversation/AGI analysis → manager router → central tools.registry → security.policy_engine → tool/provider → verification/learning`

`brains/` and `brains_v3/` remain compatibility/experimental code. They are not the authoritative entry path. New integrations must attach through `tools.registry`, not create another router.

## Configuration and secrets

All secrets must come from environment variables or a local untracked secret store. Relevant variables are listed in `.env.example`. The committed example contains no credentials.

## Ollama

Set `OLLAMA_HOST` and `JARVIS_MODEL_CHAT`. Jarvis probes availability and falls back without crashing. It never downloads a model automatically. Ollama was unavailable in the release environment, so live generation remains an environment test.

## Voice

Install a microphone backend, STT provider, and `pyttsx3` or another configured TTS backend. The state machine is `IDLE → LISTENING → PROCESSING → SPEAKING → IDLE`; listening is disabled during speaking. Missing devices return explicit errors. No physical audio device was available during release testing.

## OCR and vision

Install the Tesseract binary plus `pytesseract`, or configure a separate multimodal provider. Missing files, binaries, dependencies, and OCR failures return explicit failure results. OCR is not described as full visual understanding.

## Companion server and Android

Set a long random `JARVIS_PAIRING_SECRET`. Pairing is disabled when this variable is missing. Tokens are random, stored hashed in memory, scoped, expiring, revocable, and rate-limited. Commands pass through scope checks and the security policy.

Android source is under `android/`. Configure an HTTPS server URL. Android SDK, Gradle, emulator, and hardware were unavailable in the release environment, so APK build and hardware verification are pending.

## Google Workspace

Provide OAuth2 client configuration and tokens outside source. The integration implements Gmail read/search/send, Calendar read/create/update/delete, and Drive search/read interfaces. Writes require policy approval. Live OAuth and API tests require user credentials.

## GitHub

Set `GITHUB_TOKEN` with least-privilege repository scopes. Read operations and controlled issue creation are implemented. Writes pass through policy checks. No token was available during release testing.

## WhatsApp

The preferred provider is the official WhatsApp Cloud API using `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. The old coordinate-driven desktop scheduler remains a labeled interactive fallback and is not server-grade.

## Smart home

The provider interface models discovery, command, observed state, and verification. Home Assistant is implemented. Matter and MQTT are extension points, not claimed as connected providers. Hardware verification requires a configured Home Assistant instance and device.

## Sandbox and security

Generated Python runs in a separate isolated Python process with AST restrictions, an isolated working directory, a minimal environment, resource limits, timeout, output limits, and cleanup. This is stronger than AST-only execution, but it is not a VM/container and cannot promise kernel-level network isolation on every platform. High-risk actions require confirmation; protected system paths are refused.

## Troubleshooting

- `Ollama unavailable`: install/start Ollama and configure a model, or use the bounded fallback.
- `GUI unavailable`: install a Python build with Tk.
- `Voice unavailable`: install audio/STT/TTS dependencies and select valid devices.
- `OCR dependency unavailable`: install Tesseract and ensure it is on `PATH`.
- `server pairing disabled`: configure `JARVIS_PAIRING_SECRET` before exposing the server.
- API integration says credentials required: finish the provider's OAuth/token setup; no credential is fabricated.
