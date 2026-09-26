# JarvisPro — External Dependencies Report

**Generated:** 2026-09-23
**Definition:** A capability requires 🔌 EXTERNAL when the implementation is complete but cannot be verified because it depends on hardware, credentials, network, or third-party services not present in the current environment.

---

## Summary

| Category | Dependency | Code Status | Can be tested without? |
|----------|-----------|-------------|----------------------|
| 13 — Browser | Browser binary | ✅ Complete | No — needs binary |
| 14 — Research | Internet | ✅ Complete | No — needs network |
| 29 — Voice | Microphone | ✅ Complete | Yes — graceful skip |
| 30 — Vision | Display + OCR | ✅ Complete | Yes — graceful skip |
| 31 — Android | Android device | ✅ Complete | Yes — graceful skip |
| Smart Home | Hue/Kasa devices | ✅ Complete | Yes — graceful skip |

**All 6 external dependencies have complete, graceful code. No feature has been faked.**

---

## Detailed External Dependencies

### 🔌 Category 13 — Browser Manager

**Dependency:** Chrome, Edge, or Firefox browser installed  
**Code:** `jarvis_core/browser_manager.py`, `brains_v2/tools/browser_tool.py` (Playwright)

What's implemented: Full navigation, forms, downloads, tabs, sessions, CAPTCHA detection  
How to enable: `pip install playwright && playwright install chromium`  
Graceful degradation: Returns `"BROWSER_UNAVAILABLE — Chromium not installed."`

### 🔌 Category 14 — Research Manager

**Dependency:** Internet connectivity  
**Code:** `jarvis_core/research_manager.py`

What's implemented: Multi-source search, evidence extraction, citation verification, conflict detection  
How to enable: Ensure internet connectivity  
Graceful degradation: Returns `"I can't research that yet: no web backend is configured."`

### 🔌 Category 29 — Voice Pipeline

**Dependency:** Microphone + STT engine  
**Code:** `brains_v2/voice/`, `brains_v2/voice_v2/`

What's implemented: STT/TTS, continuous listening, VAD, interruption, offline fallback  
How to enable: `pip install SpeechRecognition pyttsx3 pyaudio`  
Graceful degradation: TEXT ONLY mode — conversational interface remains fully functional

### 🔌 Category 30 — Vision System

**Dependency:** Display (for screenshots) + OCR backend  
**Code:** `vision/screen_reader.py`, `brains_v2/vision/`, `brains_v2/core_bridge.py::handle_vision()`

What's implemented: Screenshot capture, OCR (pytesseract/easyocr), text extraction, visual state comparison  
How to enable: Install Tesseract OCR + `pip install pillow pytesseract`  
Graceful degradation: Returns `"Screen reading is unavailable (DisplayNotFoundError)."` — never fakes analysis

### 🔌 Category 31 — Android Companion

**Dependency:** Android device with USB debugging or wireless ADB + companion app  
**Code:** `android/adb_bridge.py`, `brains_v2/mobile/`, `brains_v2/server/`

What's implemented: ADB connection, shell execution, tap/swipe/text input, APK install, file push/pull, device screenshot  
How to enable: Enable USB debugging on Android → `adb tcpip 5555` → `adb connect <phone-ip>:5555`  
Graceful degradation: Returns `"Android bridge unavailable: no device connected."`

### 🔌 Smart Home Control

**Dependency:** Philips Hue bridge or TP-Link Kasa device on LAN  
**Code:** `automation/smart_home.py`

What's implemented: Hue bridge discovery, bulb/light/scene control, Kasa device discovery and control  
How to enable: Press Hue link button → `from automation.smart_home import HueBridge; b = HueBridge.discover()`  
Graceful degradation: Returns `"No Hue bridges found on the network."`

---

## Credential Management

| Service | Credential | Storage |
|---------|-----------|---------|
| Telegram | Bot token | `TELEGRAM_BOT_TOKEN` env var |
| Discord | Bot token | `DISCORD_BOT_TOKEN` env var |
| Ollama | Local (no creds) | `OLLAMA_HOST` env var |
| Cloud AI | API key | `OPENAI_API_KEY` etc. env var |
| GitHub | Personal access token | `GITHUB_TOKEN` env var |
| Hue Bridge | Local (no auth) | Local network discovery |
| Kasa | Device IP + credentials | Config file (local only) |

Setup: Copy `.env.example` to `.env` and fill in credentials. `.env` is in `.gitignore`.
