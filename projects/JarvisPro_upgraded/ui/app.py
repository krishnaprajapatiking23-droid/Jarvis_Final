"""Desktop application shell (deep-spec sections 9-15).

The shell owns settings, telemetry, workers, toasts, tray and hotkeys and
binds them to the dashboard view model. All of that is toolkit independent and
fully testable headless. The Qt window is a thin view on top: if no Qt binding
or no display is present the shell says UNAVAILABLE with the reason instead of
pretending a window opened.
"""

import importlib
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .hotkeys import HotkeyManager
from .settings import MODES, SettingsStore
from .telemetry import TelemetryProvider
from .toasts import ToastCenter
from .tray import TrayMenu
from .view_model import PAGES, DashboardViewModel
from .workers import WorkerPool

OK = "ok"
INVALID = "invalid_input"
UNAVAILABLE = "UNAVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"

QT_BINDINGS = ("PyQt6", "PyQt5", "PySide6", "PySide2")


def detect_qt() -> Dict[str, Any]:
    """Find an installed Qt binding without importing a GUI toolkit blindly."""
    tried: List[str] = []
    for name in QT_BINDINGS:
        tried.append(name)
        try:
            importlib.import_module(name)
        except Exception:
            continue
        return {"status": OK, "binding": name, "reason": None}
    return {"status": UNAVAILABLE, "binding": None,
            "reason": "no Qt binding installed (tried %s); install PyQt6 to "
                      "render the window" % ", ".join(tried)}


def headless() -> bool:
    if os.name != "posix":
        return False
    return not (os.environ.get("DISPLAY")
                or os.environ.get("WAYLAND_DISPLAY"))


class DesktopApp:
    """Toolkit-independent application shell."""

    capability = "ui"

    def __init__(self, kernel: Any = None, db_path: Optional[str] = None,
                 telemetry: Optional[TelemetryProvider] = None,
                 workers: Optional[WorkerPool] = None,
                 owner: Optional[str] = None) -> None:
        self.kernel = kernel
        self.settings = SettingsStore(db_path)
        if owner and owner not in ("owner", ""):
            self.settings.set("owner_name", owner)
        self.telemetry = telemetry or TelemetryProvider()
        self.workers = workers or WorkerPool(workers=2)
        self.toasts = ToastCenter(default_ttl=self.settings.get("toast_seconds"))
        self.tray = TrayMenu(tooltip="JARVIS")
        self.hotkeys = HotkeyManager()
        self.dashboard = DashboardViewModel(
            kernel=kernel, telemetry=self.telemetry, settings=self.settings,
            owner=self.settings.get("owner_name"))
        self.window_visible = False
        self.listening = False
        self.refresh_errors = 0
        self._loop: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.settings.on_change(self._on_setting_changed)
        self._wire_tray()
        self._wire_hotkeys()

    # ---- wiring ----
    def _wire_tray(self) -> None:
        self.tray.add("show", "Show JARVIS", handler=self.show_window)
        self.tray.add("hide", "Hide window", handler=self.hide_window)
        self.tray.add("listen", "Listening", handler=self.toggle_listening,
                      checkable=True, separator_after=True)
        self.tray.add("mode_focus", "Focus mode",
                      handler=lambda: self.dashboard.set_mode("focus"))
        self.tray.add("settings", "Settings",
                      handler=lambda: self.navigate("settings"))
        self.tray.add("quit", "Quit", handler=self.shutdown)

    def _wire_hotkeys(self) -> None:
        self.hotkeys.bind(self.settings.get("global_hotkey"), "toggle_window",
                          handler=self.toggle_window, replace=True)
        self.hotkeys.bind(self.settings.get("push_to_talk_hotkey"),
                          "push_to_talk", handler=self.toggle_listening,
                          replace=True)

    def _on_setting_changed(self, key: str, old: Any, new: Any) -> None:
        if key == "global_hotkey":
            self.hotkeys.rebind("toggle_window", new)
        elif key == "push_to_talk_hotkey":
            self.hotkeys.rebind("push_to_talk", new)
        elif key == "toast_seconds":
            self.toasts.default_ttl = float(new)
        elif key == "owner_name":
            self.dashboard.owner = new

    # ---- window / navigation ----
    def show_window(self) -> Dict[str, Any]:
        self.window_visible = True
        return {"status": OK, "visible": True}

    def hide_window(self) -> Dict[str, Any]:
        if not self.settings.get("minimise_to_tray"):
            return {"status": OK, "visible": self.window_visible,
                    "note": "minimise to tray is disabled"}
        self.window_visible = False
        return {"status": OK, "visible": False}

    def toggle_window(self) -> Dict[str, Any]:
        return self.hide_window() if self.window_visible else self.show_window()

    def toggle_listening(self) -> Dict[str, Any]:
        self.listening = not self.listening
        return {"status": OK, "listening": self.listening}

    def navigate(self, page: str) -> Dict[str, Any]:
        result = self.dashboard.navigate(page)
        if result.get("status") == OK:
            self.show_window()
        return result

    # ---- refresh ----
    def refresh(self) -> Dict[str, Any]:
        try:
            return self.dashboard.refresh()
        except Exception as exc:  # the dashboard must never crash the shell
            self.refresh_errors += 1
            return {"status": UNAVAILABLE, "error": str(exc)}

    def refresh_async(self) -> Dict[str, Any]:
        return self.workers.submit("dashboard.refresh", self.refresh,
                                   timeout=15.0)

    def start_refresh_loop(self) -> Dict[str, Any]:
        if self._loop and self._loop.is_alive():
            return {"status": OK, "running": True, "note": "already running"}
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                self.refresh_async()
                interval = max(0.25, float(
                    self.settings.get("telemetry_interval_ms") or 1000) / 1000.0)
                self._stop.wait(interval)

        self._loop = threading.Thread(target=loop, daemon=True,
                                      name="jarvis-ui-refresh")
        self._loop.start()
        return {"status": OK, "running": True}

    def stop_refresh_loop(self) -> Dict[str, Any]:
        self._stop.set()
        thread = self._loop
        if thread:
            thread.join(2.0)
        self._loop = None
        return {"status": OK, "running": False}

    # ---- commands / notifications ----
    def submit_command(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {"status": INVALID, "error": "a command is required"}
        api = getattr(self.kernel, "api", None) if self.kernel else None
        if api is not None and hasattr(api, "handle"):
            return self.workers.submit(
                "command.execute", api.handle, "command.execute",
                {"text": text.strip()})
        if self.kernel is not None and hasattr(self.kernel, "understand"):
            return self.workers.submit("kernel.understand",
                                       self.kernel.understand, text.strip())
        return {"status": NOT_CONFIGURED,
                "error": "no kernel or API is attached to accept commands"}

    def notify(self, title: str, body: str = "",
               level: str = "info") -> Dict[str, Any]:
        return self.toasts.push(title, body, level)

    # ---- settings panel ----
    def settings_panel(self) -> Dict[str, Any]:
        return {"status": OK, "schema": self.settings.schema(),
                "values": self.settings.all(),
                "history": self.settings.history(limit=10)}

    def apply_settings(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = self.settings.update(values)
        for key, error in (result.get("errors") or {}).items():
            self.toasts.push("Setting not applied", "%s: %s" % (key, error),
                             level="warning")
        if result.get("restart_required"):
            self.toasts.push("Restart required",
                             "Some changes apply after restarting JARVIS",
                             level="info")
        return result

    # ---- lifecycle ----
    def start(self) -> Dict[str, Any]:
        self.navigate(self.settings.get("start_page"))
        self.tray.show()
        snapshot = self.refresh()
        self.start_refresh_loop()
        return {"status": OK, "page": self.dashboard.page,
                "tray": self.tray.health()["status"],
                "hotkeys": self.hotkeys.health()["status"],
                "degraded": snapshot.get("degraded", [])}

    def status(self) -> Dict[str, Any]:
        qt = detect_qt()
        return {"status": OK, "visible": self.window_visible,
                "listening": self.listening, "page": self.dashboard.page,
                "mode": self.dashboard.mode(),
                "qt": qt, "headless": headless(),
                "toasts": self.toasts.health(),
                "workers": self.workers.health(),
                "hotkeys": self.hotkeys.health(),
                "tray": self.tray.health(),
                "settings": self.settings.health(),
                "telemetry": self.telemetry.health(),
                "dashboard": self.dashboard.health()}

    def health(self) -> Dict[str, Any]:
        qt = detect_qt()
        renderable = qt["status"] == OK and not headless()
        return {"available": True, "status": OK,
                "renderable": renderable,
                "reason": None if renderable else (
                    qt["reason"] or "no display attached to this session"),
                "binding": qt["binding"],
                "refresh_errors": self.refresh_errors,
                "refreshes": self.dashboard.refreshes,
                "visible": self.window_visible}

    def shutdown(self) -> Dict[str, Any]:
        self.stop_refresh_loop()
        worker = self.workers.shutdown()
        self.tray.hide()
        self.settings.close()
        self.window_visible = False
        return {"status": OK, "workers": worker}

    close = shutdown


class QtDashboard:
    """Qt view over DesktopApp. Pure rendering logic stays testable."""

    NAV_ITEMS = ("Dashboard", "AI Chat", "Voice Command", "Automation",
                 "Memory", "Files & Folders", "System Info", "Settings",
                 "About")
    TITLE = "JARVIS AI v7.0.1 PRO"

    def __init__(self, app: DesktopApp) -> None:
        self.app = app
        self.window: Any = None
        self.binding: Optional[str] = None
        self.built = False

    def build(self) -> Dict[str, Any]:
        qt = detect_qt()
        if qt["status"] != OK:
            return {"status": UNAVAILABLE, "reason": qt["reason"]}
        if headless():
            return {"status": UNAVAILABLE,
                    "reason": "no display attached to this session; the shell "
                              "still runs headless"}
        binding = qt["binding"]
        widgets = importlib.import_module("%s.QtWidgets" % binding)
        core = importlib.import_module("%s.QtCore" % binding)
        self.binding = binding
        self.qapp = (widgets.QApplication.instance()
                     or widgets.QApplication([]))
        window = widgets.QWidget()
        window.setWindowTitle(self.TITLE)
        window.resize(1440, 900)
        layout = widgets.QHBoxLayout(window)
        nav = widgets.QVBoxLayout()
        for label in self.NAV_ITEMS:
            button = widgets.QPushButton(label)
            page = label.split(" ")[0].lower().replace("&", "")
            page = {"ai": "chat", "files": "files", "system": "system",
                    "voice": "voice"}.get(page, page)
            button.clicked.connect(lambda _=False, p=page: self.app.navigate(p))
            nav.addWidget(button)
        layout.addLayout(nav)
        body = widgets.QVBoxLayout()
        self.header_label = widgets.QLabel("")
        self.reactor_label = widgets.QLabel("")
        self.detail_label = widgets.QLabel("")
        for label in (self.header_label, self.reactor_label, self.detail_label):
            body.addWidget(label)
        layout.addLayout(body)
        self.window = window
        self.built = True
        interval = int(self.app.settings.get("telemetry_interval_ms") or 1000)
        self.timer = core.QTimer(window)
        self.timer.timeout.connect(self._tick)
        self.timer.start(interval)
        return {"status": OK, "binding": binding, "title": self.TITLE}

    def _tick(self) -> None:
        # The GUI thread only queues work and paints results.
        self.app.refresh_async()
        for payload in self.app.workers.drain():
            snapshot = payload.get("result")
            if isinstance(snapshot, dict) and "header" in snapshot:
                self.paint(snapshot)

    def render(self, snapshot: Dict[str, Any]) -> Dict[str, str]:
        gauges = ((snapshot.get("header") or {}).get("gauges") or {})
        parts = []
        for name in ("cpu", "memory", "storage", "battery"):
            gauge = gauges.get(name) or {}
            if gauge.get("status") == OK:
                parts.append("%s %s%s" % (name.upper(), gauge.get("value"),
                                          gauge.get("unit", "%")))
            else:
                parts.append("%s --" % name.upper())
        reactor = snapshot.get("reactor") or {}
        system = (snapshot.get("system") or {}).get("data") or {}
        detail = "%s | %s | uptime %s" % (
            system.get("os", "unknown"),
            system.get("local_ip") or "no network",
            reactor.get("session_uptime", "0h 00m 00s"))
        return {"header": "   ".join(parts),
                "reactor": "%s - %s" % (reactor.get("state", "OFFLINE"),
                                        reactor.get("greeting", "")),
                "detail": detail}

    def paint(self, snapshot: Dict[str, Any]) -> Dict[str, str]:
        text = self.render(snapshot)
        if self.built:
            self.header_label.setText(text["header"])
            self.reactor_label.setText(text["reactor"])
            self.detail_label.setText(text["detail"])
        return text

    def run(self) -> Dict[str, Any]:
        built = self.build()
        if built["status"] != OK:
            return built
        self.window.show()
        self.qapp.exec() if hasattr(self.qapp, "exec") else self.qapp.exec_()
        return {"status": OK, "closed": True}

    def health(self) -> Dict[str, Any]:
        qt = detect_qt()
        return {"available": self.built, "status": OK if self.built else UNAVAILABLE,
                "binding": qt["binding"], "reason": qt["reason"],
                "headless": headless()}


def main(kernel: Any = None) -> Dict[str, Any]:
    app = DesktopApp(kernel=kernel)
    view = QtDashboard(app)
    result = view.run()
    if result["status"] != OK:
        snapshot = app.refresh()
        print("JARVIS desktop UI cannot render a window: %s" % result["reason"])
        print(view.render(snapshot)["header"])
        print(view.render(snapshot)["reactor"])
    app.shutdown()
    return result


if __name__ == "__main__":  # pragma: no cover
    main()
