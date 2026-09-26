"""
Desktop UI Manager — manages the desktop overlay and system tray interface.

Platform support:
  Windows: System tray icon via win32 (pywin32)
  macOS:   Status bar item viarum pscript or osascript
  Linux:   AppIndicator via gi (requires GTK3)

Install:
    pip install pywin32  # Windows system tray
    pip install pystray  # Cross-platform system tray
    pip install Pillow    # Required by pystray for icons
"""

import platform
import subprocess
import sys
from threading import Lock, Thread
from typing import Callable, List, Optional

_SYSTEM = platform.system()


class DesktopUIManager:
    """Manages desktop overlay, system tray, and notification toasts."""

    def __init__(self):
        self._tray = None
        self._notifications: List[dict] = []
        self._lock = Lock()
        self._running = False
        self._callbacks: dict = {}

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def show_tray(self, icon_path: str = None,
                  menu_items: List[tuple] = None) -> dict:
        """Show a system tray icon with optional menu."""
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return {
                "success": False,
                "error": "pystray/Pillow not installed — "
                         "run: pip install pystray Pillow",
            }

        try:
            img = Image.new("RGB", (64, 64), color="blue")
            menu = None
            if menu_items:
                menu = pystray.Menu(*[
                    pystray.MenuItem(label, lambda _: cb())
                    for label, cb in menu_items
                ])

            self._tray = pystray.Icon(
                "JARVIS",
                img,
                "JARVIS Assistant",
                menu=menu,
            )
            self._running = True
            Thread(target=self._tray.run, daemon=True).start()
            return {"success": True, "message": "Tray icon started"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def hide_tray(self) -> dict:
        """Hide/destroy the system tray icon."""
        if self._tray:
            self._tray.stop()
            self._tray = None
            self._running = False
        return {"success": True}

    def update_tray_tooltip(self, text: str) -> dict:
        """Update the tray icon tooltip text."""
        if not self._tray:
            return {"success": False, "error": "Tray not running"}
        try:
            self._tray.title = text
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Notifications / toasts
    # ------------------------------------------------------------------

    def notify(self, title: str, message: str,
               urgency: str = "normal") -> dict:
        """Show a desktop notification."""
        entry = {
            "title": title,
            "message": message,
            "urgency": urgency,
        }
        with self._lock:
            self._notifications.append(entry)

        try:
            if _SYSTEM == "Windows":
                # Windows toast via PowerShell
                ps = (
                    f'[Windows.UI.Notifications.ToastNotificationManager,'
                    f'Windows.UI.Notifications,ContentType=WindowsRuntime]'
                    f'; $xml = [Windows.UI.Notifications.ToastNotificationManager]'
                    f'::GetTemplateContent('
                    f'[Windows.UI.Notifications.ToastTemplateType]::ToastText02);'
                    f'$text = $xml.GetElementsByTagName("text");'
                    f'$text[0].AppendChild($xml.CreateTextNode("{title}")) | Out-Null;'
                    f'$text[1].AppendChild($xml.CreateTextNode("{message}")) | Out-Null;'
                    f'$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);'
                    f'[Windows.UI.Notifications.ToastNotificationManager]'
                    f'::CreateToastNotifier("JARVIS").Show($toast)'
                )
                subprocess.Popen(
                    ["powershell", "-Command", ps],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            elif _SYSTEM == "Linux":
                subprocess.Popen(
                    ["notify-send", title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            elif _SYSTEM == "Darwin":
                subprocess.Popen(
                    ["osascript", "-e",
                     f'display notification "{message}" with title "{title}"'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
        except Exception:
            pass  # Non-fatal

        return {"success": True, "title": title}

    # ------------------------------------------------------------------
    # Window overlay hint
    # ------------------------------------------------------------------

    def overlay_message(self, text: str, duration_s: int = 3) -> dict:
        """Flash a brief message on screen (platform-specific)."""
        if _SYSTEM == "Windows":
            try:
                ps = (
                    f'Add-Type -AssemblyName System.Windows.Forms; '
                    f'$b = New-Object System.Windows.Forms.Label; '
                    f'$b.Text = "{text}"; '
                    f'$b.Font = New-Object System.Drawing.Font("Arial",24); '
                    f'$b.BackColor = "Navy"; '
                    f'$b.ForeColor = "White"; '
                    f'$b.AutoSize = $true; '
                    f'$f = New-Object System.Windows.Forms.Form; '
                    f'$f.Controls.Add($b); '
                    f'$f.BackColor = "Navy"; '
                    f'$f.FormBorderStyle = "None"; '
                    f'$f.StartPosition = "CenterScreen"; '
                    f'$f.WindowState = "Normal"; '
                    f'$f.Opacity = 0.9; '
                    f'$f.Show(); '
                    f'start-sleep -Seconds {duration_s}; '
                    f'$f.Close()'
                )
                subprocess.Popen(
                    ["powershell", "-Command", ps],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            except Exception:
                pass
        return {"success": True, "message": text}

    def notifications(self, limit: int = 20) -> List[dict]:
        with self._lock:
            return self._notifications[-limit:]


_manager = DesktopUIManager()

show_tray = _manager.show_tray
hide_tray = _manager.hide_tray
notify = _manager.notify
overlay_message = _manager.overlay_message
notifications = _manager.notifications
update_tray_tooltip = _manager.update_tray_tooltip
