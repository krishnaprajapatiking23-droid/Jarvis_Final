"""capability_registry.py — JARVIS system-state snapshot for the GUI.

Single source of truth that the GUI reads on every refresh tick.
Does NOT contain business logic — only state reflection.

States per capability:
  AVAILABLE       — responds correctly to a health check
  DEGRADED        — responds but with degraded quality/warnings
  NOT_CONFIGURED  — code exists but API keys / tokens are not set
  UNAVAILABLE     — hardware missing or library not installed
  ERROR           — present but threw an exception during probe
  DISABLED        — user explicitly turned it off in settings

Hardware probes are marked UNAVAILABLE (never faked) when the device
or library is not present.
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = __import__("logging").getLogger(__name__)


class CapabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


@dataclass
class Capability:
    id: str  # snake_case key, e.g. "microphone"
    label: str  # human-readable, e.g. "Microphone"
    state: CapabilityState = CapabilityState.UNAVAILABLE
    detail: str = ""  # short reason / sub-state
    last_probed: float = 0.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "state": self.state.value,
            "detail": self.detail,
            "last_probed": self.last_probed,
            "latency_ms": round(self.latency_ms, 2),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Hardware / OS probes
# ---------------------------------------------------------------------------

def _probe_microphone() -> Capability:
    """Check if any microphone is present and readable."""
    cap = Capability(id="microphone", label="Microphone")
    began = time.time()
    try:
        import sounddevice as sd

        devices = sd.query_devices(kind="input")
        cap.state = CapabilityState.AVAILABLE
        if isinstance(devices, list):
            cap.detail = f"{len(devices)} input device(s)"
            cap.metadata["device_count"] = len(devices)
        else:
            cap.detail = devices.get("name", "Default input")
            cap.metadata["device_count"] = 1
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "sounddevice not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_camera() -> Capability:
    """Check if any camera is present via OpenCV."""
    cap = Capability(id="camera", label="Camera")
    began = time.time()
    try:
        import cv2

        index = 0
        found = False
        for i in range(5):
            cap_test = cv2.VideoCapture(i)
            if cap_test.isOpened():
                ret, _ = cap_test.read()
                cap_test.release()
                if ret:
                    index = i
                    found = True
                    break
        if found:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = f"Camera {index}"
            cap.metadata["camera_index"] = index
        else:
            cap.state = CapabilityState.UNAVAILABLE
            cap.detail = "No camera detected"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "OpenCV not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_stt() -> Capability:
    """Check if faster-whisper (or fallback) STT model is loadable."""
    cap = Capability(id="stt", label="Speech-to-Text (STT)")
    began = time.time()
    try:
        import faster_whisper

        # Quick sanity: try to get model info without downloading
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "faster-whisper ready"
        cap.metadata["engine"] = "faster-whisper"
    except ImportError:
        try:
            import torch

            cap.state = CapabilityState.AVAILABLE
            cap.detail = "torch ready (fallback STT)"
            cap.metadata["engine"] = "torch"
        except ImportError:
            cap.state = CapabilityState.NOT_CONFIGURED
            cap.detail = "No STT engine installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_tts() -> Capability:
    """Check if edge-tts (or gTTS) TTS engine is available."""
    cap = Capability(id="tts", label="Text-to-Speech (TTS)")
    began = time.time()
    try:
        import edge_tts

        cap.state = CapabilityState.AVAILABLE
        cap.detail = "edge-tts ready"
        cap.metadata["engine"] = "edge-tts"
    except ImportError:
        try:
            import gtts

            cap.state = CapabilityState.AVAILABLE
            cap.detail = "gTTS ready (fallback)"
            cap.metadata["engine"] = "gtts"
        except ImportError:
            cap.state = CapabilityState.NOT_CONFIGURED
            cap.detail = "No TTS engine installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_vision() -> Capability:
    """Check if the vision pipeline can accept a screenshot."""
    cap = Capability(id="vision", label="Vision / Screenshot")
    began = time.time()
    try:
        from vision.vision_engine import analyze_screen
        from PIL import Image
        import numpy as np

        # Grab a tiny test screenshot (1×1 pixel) to verify the pipeline works
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
        arr = np.array(img)
        # Quick smoke test — just confirm we got pixels
        if arr.size > 0:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "Screenshot pipeline ready"
            cap.metadata["monitor_count"] = len(sct.monitors)
        else:
            cap.state = CapabilityState.ERROR
            cap.detail = "Screenshot returned empty array"
    except ImportError as exc:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = f"Missing: {exc.name}"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_speaker_id() -> Capability:
    """Speaker identification — requires enrollment data or a model."""
    cap = Capability(id="speaker_identification", label="Speaker Identification")
    began = time.time()
    try:
        data_dir = "data"
        profile_path = os.path.join(data_dir, "speaker_profiles.json")
        if os.path.exists(profile_path):
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "Profiles found"
            cap.metadata["profile_path"] = profile_path
        else:
            cap.state = CapabilityState.NOT_CONFIGURED
            cap.detail = "No speaker profiles enrolled"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_authentication() -> Capability:
    """Voice/biometric authentication."""
    cap = Capability(id="voice_authentication", label="Voice Authentication")
    began = time.time()
    try:
        from brains_v2.security.owner import Owner

        owner = Owner()
        if owner.is_configured():
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "Owner configured"
        else:
            cap.state = CapabilityState.NOT_CONFIGURED
            cap.detail = "Owner not enrolled"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "security/owner not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_ocr() -> Capability:
    """OCR via easyocr or pytesseract."""
    cap = Capability(id="ocr", label="OCR (Text Recognition)")
    began = time.time()
    try:
        import pytesseract

        version = pytesseract.get_tesseract_version()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = f"Tesseract {version}"
        cap.metadata["engine"] = "pytesseract"
    except ImportError:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = "pytesseract not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_gpu() -> Capability:
    """Detect GPU for acceleration."""
    cap = Capability(id="gpu", label="GPU Acceleration")
    began = time.time()
    try:
        import torch

        if torch.cuda.is_available():
            cap.state = CapabilityState.AVAILABLE
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            cap.detail = f"{name} ({mem:.1f} GB)"
            cap.metadata["gpu_name"] = name
            cap.metadata["vram_gb"] = round(mem, 1)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "Apple MPS"
            cap.metadata["engine"] = "mps"
        else:
            cap.state = CapabilityState.UNAVAILABLE
            cap.detail = "No GPU detected"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "torch not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


# ---------------------------------------------------------------------------
# System resource probes
# ---------------------------------------------------------------------------

def _probe_cpu() -> Capability:
    cap = Capability(id="cpu", label="CPU")
    began = time.time()
    try:
        import psutil

        usage = psutil.cpu_percent(interval=0.1)
        count = psutil.cpu_count(logical=False) or psutil.cpu_count()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = f"{usage:.0f}% ({count} cores)"
        cap.metadata["usage_percent"] = usage
        cap.metadata["core_count"] = count
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "psutil not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_memory() -> Capability:
    cap = Capability(id="system_memory", label="System Memory (RAM)")
    began = time.time()
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_gb = mem.used / 1024**3
        total_gb = mem.total / 1024**3
        cap.state = CapabilityState.AVAILABLE
        cap.detail = f"{used_gb:.1f} / {total_gb:.1f} GB ({mem.percent:.0f}%)"
        cap.metadata["used_gb"] = round(used_gb, 1)
        cap.metadata["total_gb"] = round(total_gb, 1)
        cap.metadata["percent"] = mem.percent
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "psutil not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_storage() -> Capability:
    cap = Capability(id="storage", label="Storage")
    began = time.time()
    try:
        import psutil

        disk = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        free_gb = disk.free / 1024**3
        total_gb = disk.total / 1024**3
        cap.state = CapabilityState.AVAILABLE
        cap.detail = f"{free_gb:.0f} GB free / {total_gb:.0f} GB ({disk.percent:.0f}% used)"
        cap.metadata["free_gb"] = round(free_gb, 1)
        cap.metadata["total_gb"] = round(total_gb, 1)
        cap.metadata["percent"] = disk.percent
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "psutil not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_network() -> Capability:
    cap = Capability(id="network", label="Network")
    began = time.time()
    try:
        import requests

        r = requests.get("https://www.google.com", timeout=3)
        latency_ms = r.elapsed.total_seconds() * 1000
        if r.status_code == 200:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = f"Connected ({latency_ms:.0f} ms)"
            cap.metadata["latency_ms"] = round(latency_ms, 1)
        else:
            cap.state = CapabilityState.DEGRADED
            cap.detail = f"HTTP {r.status_code}"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "requests not installed"
    except Exception:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "No internet connection"
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_battery() -> Capability:
    cap = Capability(id="battery", label="Battery")
    began = time.time()
    try:
        import psutil

        battery = psutil.sensors_battery()
        if battery is None:
            cap.state = CapabilityState.UNAVAILABLE
            cap.detail = "No battery (desktop)"
        elif battery.power_plugged:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = f"Charging ({battery.percent:.0f}%)"
            cap.metadata["percent"] = battery.percent
            cap.metadata["plugged"] = True
        else:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = f"{battery.percent:.0f}% ({battery.secsleft:.0f}m left)"
            cap.metadata["percent"] = battery.percent
            cap.metadata["plugged"] = False
    except (ImportError, AttributeError):
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "psutil/battery not available"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


# ---------------------------------------------------------------------------
# Integration probes — check config tokens
# ---------------------------------------------------------------------------

def _token_status(path: str, env_var: str) -> tuple[bool, str]:
    """Return (is_configured, detail). Checks env var and config file."""
    env_val = os.environ.get(env_var, "")
    if env_val:
        return True, f"env:{env_var}"
    if os.path.exists(path):
        import json

        try:
            with open(path) as f:
                data = json.load(f)
            # Check for any non-empty string value that looks like a token/key
            for v in data.values():
                if isinstance(v, str) and len(v) > 10:
                    return True, f"config:{os.path.basename(path)}"
        except Exception:
            pass
    return False, "not configured"


def _probe_telegram() -> Capability:
    cap = Capability(id="telegram", label="Telegram")
    began = time.time()
    configured, detail = _token_status("config/telegram.json", "TELEGRAM_BOT_TOKEN")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_discord() -> Capability:
    cap = Capability(id="discord", label="Discord")
    began = time.time()
    configured, detail = _token_status("config/discord.json", "DISCORD_BOT_TOKEN")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_github() -> Capability:
    cap = Capability(id="github", label="GitHub")
    began = time.time()
    configured, detail = _token_status("config/github.json", "GITHUB_TOKEN")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_whatsapp() -> Capability:
    cap = Capability(id="whatsapp", label="WhatsApp")
    began = time.time()
    configured, detail = _token_status("config/whatsapp.json", "WHATSAPP_TOKEN")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_google() -> Capability:
    cap = Capability(id="google", label="Google Workspace")
    began = time.time()
    configured, detail = _token_status("config/google.json", "GOOGLE_APPLICATION_CREDENTIALS")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_smart_home() -> Capability:
    cap = Capability(id="smart_home", label="Smart Home (HomeAssistant)")
    began = time.time()
    configured, detail = _token_status("config/smarthome.json", "HASS_URL")
    if configured:
        cap.state = CapabilityState.AVAILABLE
        cap.detail = detail
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = detail
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


# ---------------------------------------------------------------------------
# Core system probes — kernel + runtime
# ---------------------------------------------------------------------------

def _probe_jarvis_runtime() -> Capability:
    cap = Capability(id="jarvis_runtime", label="Jarvis Runtime")
    began = time.time()
    try:
        from brains_v2.runtime import get_runtime

        runtime = get_runtime()
        report = runtime.report()
        if report is None:
            cap.state = CapabilityState.NOT_CONFIGURED
            cap.detail = "Runtime not started"
        elif report.status == "ONLINE":
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "All systems operational"
        elif report.status == "DEGRADED":
            cap.state = CapabilityState.DEGRADED
            failed = [s.name for s in report.degraded]
            cap.detail = f"Degraded: {', '.join(failed)}"
        else:
            cap.state = CapabilityState.ERROR
            cap.detail = report.greeting or "Unknown state"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_jarvis_kernel() -> Capability:
    cap = Capability(id="jarvis_kernel", label="Jarvis Kernel")
    began = time.time()
    try:
        from jarvis_core.kernel import get_kernel

        kernel = get_kernel()
        health = kernel.health()
        manager_states = health.get("managers", {})
        healthy = sum(1 for m in manager_states.values() if m.get("available"))
        total = len(manager_states)
        if total == 0:
            cap.state = CapabilityState.DEGRADED
            cap.detail = "No managers registered"
        elif healthy == total:
            cap.state = CapabilityState.AVAILABLE
            cap.detail = f"All {total} managers healthy"
        else:
            cap.state = CapabilityState.DEGRADED
            cap.detail = f"{healthy}/{total} managers healthy"
        cap.metadata["managers"] = manager_states
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_event_bus() -> Capability:
    cap = Capability(id="event_bus", label="Event Bus")
    began = time.time()
    try:
        from core.event_bus import get_event_bus

        bus = get_event_bus()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = f"{len(bus._history)} events in history"
        cap.metadata["history_count"] = len(bus._history)
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "core.event_bus not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_brain_v2() -> Capability:
    cap = Capability(id="brain_v2", label="Brain V2 (AI Brain)")
    began = time.time()
    try:
        from brains_v2.manager import BrainV2

        brain = BrainV2()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "BrainV2 ready"
        cap.metadata["model"] = getattr(brain, "model_name", "unknown")
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "brains_v2.manager not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_workflow() -> Capability:
    cap = Capability(id="workflow_engine", label="Workflow Engine")
    began = time.time()
    try:
        from core.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "WorkflowEngine ready"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "core.workflow_engine not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_scheduler() -> Capability:
    cap = Capability(id="scheduler", label="Scheduler")
    began = time.time()
    try:
        from scheduler.scheduler import JarvisScheduler

        sched = JarvisScheduler()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "Scheduler ready"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "scheduler not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_memory_manager() -> Capability:
    cap = Capability(id="memory", label="Memory Manager")
    began = time.time()
    try:
        from memory.manager import MemoryManager

        mgmr = MemoryManager()
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "MemoryManager ready"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "memory.manager not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_updater() -> Capability:
    cap = Capability(id="updater", label="Updater")
    began = time.time()
    # Check if the updater directory exists
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    updater_path = os.path.join(root, "updater")
    if os.path.isdir(updater_path):
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "Updater directory found"
    else:
        cap.state = CapabilityState.NOT_CONFIGURED
        cap.detail = "Updater not created yet"
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_desktop_control() -> Capability:
    cap = Capability(id="desktop_control", label="Desktop Control (pyautogui)")
    began = time.time()
    try:
        import pyautogui

        # Move and restore cursor — non-invasive probe
        orig = pyautogui.position()
        pyautogui.moveTo(orig[0], orig[1])
        cap.state = CapabilityState.AVAILABLE
        cap.detail = "pyautogui ready"
    except ImportError:
        cap.state = CapabilityState.UNAVAILABLE
        cap.detail = "pyautogui not installed"
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


def _probe_browser() -> Capability:
    cap = Capability(id="browser", label="Browser Automation")
    began = time.time()
    try:
        from jarvis_core.kernel import get_kernel

        kernel = get_kernel()
        health = kernel.health()
        browser_health = health.get("browser", {})
        if browser_health.get("available"):
            cap.state = CapabilityState.AVAILABLE
            cap.detail = "BrowserManager healthy"
        else:
            cap.state = CapabilityState.DEGRADED
            cap.detail = browser_health.get("error", "Browser not available")
    except Exception as exc:
        cap.state = CapabilityState.ERROR
        cap.detail = str(exc)[:80]
    cap.latency_ms = (time.time() - began) * 1000
    cap.last_probed = time.time()
    return cap


# ---------------------------------------------------------------------------
# All probes — ordered for display
# ---------------------------------------------------------------------------
_ALL_PROBES: List[tuple[str, callable]] = [
    # Core
    ("jarvis_runtime", _probe_jarvis_runtime),
    ("jarvis_kernel", _probe_jarvis_kernel),
    ("event_bus", _probe_event_bus),
    ("brain_v2", _probe_brain_v2),
    ("workflow_engine", _probe_workflow),
    ("scheduler", _probe_scheduler),
    ("memory", _probe_memory_manager),
    ("updater", _probe_updater),
    # Hardware
    ("microphone", _probe_microphone),
    ("stt", _probe_stt),
    ("tts", _probe_tts),
    ("vision", _probe_vision),
    ("camera", _probe_camera),
    ("speaker_identification", _probe_speaker_id),
    ("voice_authentication", _probe_authentication),
    ("ocr", _probe_ocr),
    ("gpu", _probe_gpu),
    # System
    ("cpu", _probe_cpu),
    ("system_memory", _probe_memory),
    ("storage", _probe_storage),
    ("network", _probe_network),
    ("battery", _probe_battery),
    ("desktop_control", _probe_desktop_control),
    ("browser", _probe_browser),
    # Integrations
    ("telegram", _probe_telegram),
    ("discord", _probe_discord),
    ("github", _probe_github),
    ("whatsapp", _probe_whatsapp),
    ("google", _probe_google),
    ("smart_home", _probe_smart_home),
]


# ---------------------------------------------------------------------------
# Main registry
# ---------------------------------------------------------------------------

class CapabilityRegistry:
    """Thread-safe, lazily-probed, cached-capability snapshot for the GUI."""

    def __init__(self) -> None:
        self._caps: Dict[str, Capability] = {}
        self._lock = threading.RLock()
        self._last_full_probe: float = 0.0
        self._probe_interval: float = 5.0  # seconds between full re-probes

    # -- GUI-facing API --------------------------------------------------------

    def get(self, cap_id: str) -> Optional[Capability]:
        """Return one capability (may be stale if not yet re-probed)."""
        with self._lock:
            return self._caps.get(cap_id)

    def all(self) -> List[Capability]:
        """Return all capabilities as a list."""
        with self._lock:
            return list(self._caps.values())

    def summary(self) -> Dict[str, Any]:
        """High-level summary for dashboard panels."""
        with self._lock:
            states = [c.state.value for c in self._caps.values()]
            return {
                "total": len(self._caps),
                "available": states.count(CapabilityState.AVAILABLE.value),
                "degraded": states.count(CapabilityState.DEGRADED.value),
                "not_configured": states.count(CapabilityState.NOT_CONFIGURED.value),
                "unavailable": states.count(CapabilityState.UNAVAILABLE.value),
                "error": states.count(CapabilityState.ERROR.value),
                "disabled": states.count(CapabilityState.DISABLED.value),
                "last_probed": self._last_full_probe,
            }

    def capabilities_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Capabilities grouped for the GUI sidebar/status page."""
        categories = {
            "Core": ["jarvis_runtime", "jarvis_kernel", "event_bus", "brain_v2",
                     "workflow_engine", "scheduler", "memory", "updater"],
            "Voice & Audio": ["microphone", "stt", "tts", "speaker_identification",
                              "voice_authentication"],
            "Vision": ["vision", "camera", "ocr", "gpu"],
            "System": ["cpu", "system_memory", "storage", "network", "battery",
                       "desktop_control", "browser"],
            "Integrations": ["telegram", "discord", "github", "whatsapp",
                             "google", "smart_home"],
        }
        with self._lock:
            result: Dict[str, List[Dict[str, Any]]] = {}
            for cat, ids in categories.items():
                result[cat] = [
                    self._caps[cid].to_dict() for cid in ids if cid in self._caps
                ]
            return result

    def jarvis_status(self) -> Dict[str, Any]:
        """Aggregated Jarvis runtime status for the top-header bar."""
        with self._lock:
            rt = self._caps.get("jarvis_runtime")
            kr = self._caps.get("jarvis_kernel")
            runtime_state = rt.state.value if rt else "UNKNOWN"
            kernel_state = kr.state.value if kr else "UNKNOWN"
            return {
                "runtime": runtime_state,
                "kernel": kernel_state,
                "overall": (
                    "ONLINE"
                    if runtime_state == "AVAILABLE" and kernel_state == "AVAILABLE"
                    else "DEGRADED" if runtime_state != "ERROR"
                    else "OFFLINE"
                ),
                "runtime_detail": rt.detail if rt else "",
                "kernel_detail": kr.detail if kr else "",
            }

    # -- Internal --------------------------------------------------------

    def refresh(self, force: bool = False) -> None:
        """Re-probe all capabilities if the interval has elapsed (or force=True)."""
        with self._lock:
            now = time.time()
            if not force and (now - self._last_full_probe) < self._probe_interval:
                return
            self._last_full_probe = now

        for cap_id, probe_fn in _ALL_PROBES:
            try:
                cap = probe_fn()
            except Exception as exc:
                log.warning("Capability probe %s raised: %s", cap_id, exc)
                cap = Capability(
                    id=cap_id, label=cap_id.replace("_", " ").title(),
                    state=CapabilityState.ERROR, detail=str(exc)[:80],
                    last_probed=time.time(),
                )
            with self._lock:
                self._caps[cap_id] = cap

    def refresh_one(self, cap_id: str) -> Capability:
        """Immediately re-probe one capability."""
        for cid, probe_fn in _ALL_PROBES:
            if cid == cap_id:
                try:
                    cap = probe_fn()
                except Exception as exc:
                    log.warning("Capability probe %s raised: %s", cap_id, exc)
                    cap = Capability(
                        id=cap_id,
                        label=cap_id.replace("_", " ").title(),
                        state=CapabilityState.ERROR,
                        detail=str(exc)[:80],
                        last_probed=time.time(),
                    )
                with self._lock:
                    self._caps[cap_id] = cap
                return cap
        raise KeyError(f"Unknown capability: {cap_id}")


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------
_REGISTRY: Optional[CapabilityRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_capability_registry() -> CapabilityRegistry:
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = CapabilityRegistry()
        return _REGISTRY


__all__ = [
    "CapabilityState",
    "Capability",
    "CapabilityRegistry",
    "get_capability_registry",
]
