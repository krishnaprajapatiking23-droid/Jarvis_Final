"""
Android Manager — controls an Android device via ADB (Android Debug Bridge).

Requires: adb installed and accessible on PATH.
Install ADB: https://developer.android.com/studio/releases/platform-tools

Common install:
    pip install pure-python-adb  # pure Python fallback
    # or rely on system adb binary
"""

import subprocess
from threading import Lock
from typing import Optional, List, Dict


class AndroidManager:

    def __init__(self, device_id: str = None):
        self._device_id = device_id  # None = first connected device
        self._lock = Lock()

    # ------------------------------------------------------------------
    # ADB helpers
    # ------------------------------------------------------------------

    def _run(self, *args) -> Dict:
        cmd = ["adb"]
        if self._device_id:
            cmd.extend(["-s", self._device_id])
        cmd.extend(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "code": result.returncode,
            }
        except FileNotFoundError:
            return {"success": False, "error": "adb not found on PATH"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "ADB command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def devices(self) -> List[Dict]:
        """List all connected ADB devices."""
        res = self._run("devices")
        if not res["success"]:
            return [{"serial": "error", "state": res.get("error", "unknown")}]
        lines = [l for l in res["stdout"].splitlines() if l.strip()
                 and not l.startswith("List")]
        devices = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"serial": parts[0], "state": parts[1]})
        return devices

    def shell(self, command: str) -> Dict:
        """Run a shell command on the device."""
        return self._run("shell", command)

    def install(self, apk_path: str) -> Dict:
        """Install an APK (requires full path on host)."""
        return self._run("install", "-r", apk_path)

    def uninstall(self, package: str) -> Dict:
        """Uninstall an app by package name."""
        return self._run("uninstall", package)

    def screenshot(self, save_path: str = "android_screenshot.png") -> Dict:
        """Capture device screen and save to host path."""
        pull_result = self._run("exec-out", "screencap", "-p")
        if pull_result["success"] and pull_result["stdout"]:
            try:
                with open(save_path, "wb") as f:
                    f.write(pull_result["stdout"].encode("latin1"))
                return {"success": True, "path": save_path}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "screencap failed"}

    def tap(self, x: int, y: int) -> Dict:
        """Tap screen at coordinates."""
        return self.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300) -> Dict:
        """Swipe from (x1,y1) to (x2,y2)."""
        return self.shell(
            f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def input_text(self, text: str) -> Dict:
        """Type text on the device."""
        escaped = text.replace(" ", "%s")
        return self.shell(f"input text {escaped}")

    def press_key(self, keycode: str) -> Dict:
        """Press a keycode (e.g. HOME, BACK, ENTER)."""
        return self.shell(f"input keyevent {keycode}")

    def current_app(self) -> Dict:
        """Get the currently focused app's package and activity."""
        res = self.shell(
            "dumpsys activity activities | grep mResumedActivity")
        return {"output": res.get("stdout", "")}

    def list_packages(self) -> List[str]:
        """List installed packages."""
        res = self.shell("pm list packages")
        if res["success"]:
            return [l.replace("package:", "").strip()
                    for l in res["stdout"].splitlines()]
        return []

    def start_app(self, package: str, activity: str = None) -> Dict:
        """Launch an app by package name (and optional activity)."""
        if activity:
            return self.shell(
                f"am start -n {package}/{activity}")
        return self.shell(f"am start -n {package}")


_manager = AndroidManager()

devices = _manager.devices
shell = _manager.shell
install = _manager.install
uninstall = _manager.uninstall
screenshot = _manager.screenshot
tap = _manager.tap
swipe = _manager.swipe
input_text = _manager.input_text
press_key = _manager.press_key
current_app = _manager.current_app
list_packages = _manager.list_packages
start_app = _manager.start_app
