"""
Computer Automation Manager — controls the local machine via automation.

Supports (platform-detected):
  Windows: pyautogui / pywinauto / win32com
  macOS:   pyatom / subprocess osascript
  Linux:   pyautogui / subprocess xdotool

Install automation deps:
  pip install pyautogui pyperclip
"""

import platform
import subprocess
import sys
from threading import Lock

_SYSTEM = platform.system()


class ComputerAutomationManager:
    """High-level computer control: mouse, keyboard, windows, clipboard."""

    def __init__(self):
        self._history = []
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Core automation
    # ------------------------------------------------------------------

    def click(self, x: int = None, y: int = None, button: str = "left",
              clicks: int = 1) -> dict:
        """Click at coordinates (or current cursor position)."""
        try:
            import pyautogui
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            return self._ok(f"Clicked {button} at ({x}, {y})")
        except ImportError:
            return self._err("pyautogui not installed — run: pip install pyautogui")
        except Exception as e:
            return self._err(str(e))

    def move(self, x: int, y: int, duration: float = 0.3) -> dict:
        """Move the mouse to (x, y)."""
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return self._ok(f"Moved to ({x}, {y})")
        except ImportError:
            return self._err("pyautogui not installed")
        except Exception as e:
            return self._err(str(e))

    def typewrite(self, text: str, interval: float = 0.05) -> dict:
        """Type text as keyboard input."""
        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            return self._ok(f"Typed: {text[:30]}...")
        except ImportError:
            return self._err("pyautogui not installed")
        except Exception as e:
            return self._err(str(e))

    def press(self, key: str) -> dict:
        """Press a single key (e.g. 'enter', 'ctrl', 'alt', 'tab')."""
        try:
            import pyautogui
            pyautogui.press(key)
            return self._ok(f"Pressed: {key}")
        except ImportError:
            return self._err("pyautogui not installed")
        except Exception as e:
            return self._err(str(e))

    def hotkey(self, *keys) -> dict:
        """Press a hotkey combination (e.g. 'ctrl', 'c')."""
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            return self._ok(f"Hotkey: {'+'.join(keys)}")
        except ImportError:
            return self._err("pyautogui not installed")
        except Exception as e:
            return self._err(str(e))

    def screenshot(self, path: str = None) -> dict:
        """Take a screenshot, optionally saving to path."""
        try:
            import pyautogui
            img = pyautogui.screenshot()
            if path:
                img.save(path)
                return self._ok(f"Saved screenshot to {path}")
            return self._ok("Screenshot captured", data={"size": img.size})
        except ImportError:
            return self._err("pyautogui not installed")
        except Exception as e:
            return self._err(str(e))

    def window_list(self) -> list:
        """List open windows (Windows via pywin32)."""
        try:
            if _SYSTEM == "Windows":
                import win32gui
                results = []
                win32gui.EnumWindows(
                    lambda hwnd, _: results.append(
                        win32gui.GetWindowText(hwnd)), None)
                return [t for t in results if t]
            return ["(window listing not supported on this platform)"]
        except ImportError:
            return ["win32gui not installed — run: pip install pywin32"]
        except Exception as e:
            return [f"Error: {e}"]

    def open_app(self, name: str) -> dict:
        """Launch an application by name."""
        try:
            if _SYSTEM == "Windows":
                subprocess.Popen(f"start {name}", shell=True)
            elif _SYSTEM == "Darwin":
                subprocess.Popen(["open", "-a", name])
            else:
                subprocess.Popen(name.split())
            return self._ok(f"Opened: {name}")
        except Exception as e:
            return self._err(str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ok(self, message: str, data: dict = None) -> dict:
        return {"success": True, "message": message, "data": data}

    def _err(self, message: str) -> dict:
        return {"success": False, "message": message}


_manager = ComputerAutomationManager()

click = _manager.click
move = _manager.move
typewrite = _manager.typewrite
press = _manager.press
hotkey = _manager.hotkey
screenshot = _manager.screenshot
window_list = _manager.window_list
open_app = _manager.open_app
