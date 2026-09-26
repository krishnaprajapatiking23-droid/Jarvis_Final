"""JARVIS desktop UI subsystem (deep-spec sections 9-15).

The logic layer (telemetry, settings, hotkeys, workers, toasts, tray, view
model) is toolkit independent and testable headless. The Qt window in app.py
is a thin view and honestly reports UNAVAILABLE when no binding or display is
present.
"""

from .telemetry import (HISTORY_SIZE, CpuSampler, TelemetryProvider, battery,
                        format_duration, host_info, memory, network, storage,
                        uptime)
from .workers import (CANCELLED, DONE, FAILED, PENDING, RUNNING, TIMEOUT, Job,
                      WorkerPool)
from .settings import MODES, SCHEMA, START_PAGES, THEMES, Setting, SettingsStore
from .hotkeys import (MODIFIERS, RESERVED, HotkeyManager, HotkeyProvider,
                      NullHotkeyProvider, normalise)
from .tray import NullTrayProvider, TrayMenu, TrayProvider
from .toasts import LEVELS, ToastCenter
from .view_model import PAGES, QUICK_ACTIONS, DashboardViewModel
from .app import QT_BINDINGS, DesktopApp, QtDashboard, detect_qt, headless

__all__ = [
    "TelemetryProvider", "CpuSampler", "format_duration", "host_info",
    "memory", "storage", "battery", "network", "uptime", "HISTORY_SIZE",
    "WorkerPool", "Job", "DONE", "FAILED", "CANCELLED", "TIMEOUT", "PENDING",
    "RUNNING", "SettingsStore", "Setting", "SCHEMA", "THEMES", "MODES",
    "START_PAGES", "HotkeyManager", "HotkeyProvider", "NullHotkeyProvider",
    "normalise", "MODIFIERS", "RESERVED", "TrayMenu", "TrayProvider",
    "NullTrayProvider", "ToastCenter", "LEVELS", "DashboardViewModel",
    "PAGES", "QUICK_ACTIONS", "DesktopApp", "QtDashboard", "detect_qt",
    "headless", "QT_BINDINGS",
]
