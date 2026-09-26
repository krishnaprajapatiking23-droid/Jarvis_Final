"""
Android ADB Bridge — PC ↔ Android Companion App Communication

Provides ADB-based device management for the Android companion app.
Requires: adb installed, USB debugging or wireless ADB enabled on Android device.
"""

import subprocess
import socket
import time
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ADBBridge:
    """Manages ADB connection to Android device for JARVIS companion app."""

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id  # None = first/only device
        self._connected = False
        self._device_info: Dict[str, str] = {}

    def is_available(self) -> bool:
        """Check if ADB is available and at least one device is connected."""
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split('\n')
            # Line 0 is "List of devices attached", rest are devices
            for line in lines[1:]:
                if line.strip() and 'device' in line:
                    self._connected = True
                    return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def connect_wireless(self, ip: str, port: int = 5555) -> bool:
        """Connect to Android device over WiFi. Requires prior USB pairing."""
        try:
            subprocess.run(
                ['adb', 'connect', f'{ip}:{port}'],
                capture_output=True, timeout=10
            )
            self.device_id = f'{ip}:{port}'
            return self.is_connected()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def disconnect(self) -> bool:
        """Disconnect from Android device."""
        if self.device_id:
            try:
                subprocess.run(
                    ['adb', '-s', self.device_id, 'disconnect'],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass
        self._connected = False
        self.device_id = None
        return True

    def is_connected(self) -> bool:
        """Check current connection status."""
        if not self.device_id:
            return self.is_available()
        try:
            result = subprocess.run(
                ['adb', '-s', self.device_id, 'get-state'],
                capture_output=True, text=True, timeout=5
            )
            self._connected = 'device' in result.stdout
            return self._connected
        except Exception:
            return False

    def get_device_info(self) -> Dict[str, str]:
        """Get Android device info (model, Android version, battery, etc.)."""
        if not self.is_connected():
            return {}
        info = {}
        cmds = {
            'model': ['adb', '-s', self.device_id, 'shell', 'getprop', 'ro.product.model'],
            'manufacturer': ['adb', '-s', self.device_id, 'shell', 'getprop', 'ro.product.manufacturer'],
            'android_version': ['adb', '-s', self.device_id, 'shell', 'getprop', 'ro.build.version.release'],
            'battery': ['adb', '-s', self.device_id, 'shell', 'dumpsys', 'battery', '-l'],
            'screen_state': ['adb', '-s', self.device_id, 'shell', 'dumpsys', 'power'],
        }
        for key, cmd in cmds.items():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                info[key] = result.stdout.strip()
            except Exception:
                info[key] = 'unavailable'
        self._device_info = info
        return info

    def send_command(self, command: str) -> str:
        """Send shell command to Android device and return output."""
        if not self.is_connected():
            return '{"error": "device_not_connected"}'
        try:
            result = subprocess.run(
                ['adb', '-s', self.device_id, 'shell', command],
                capture_output=True, text=True, timeout=15
            )
            return result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            return '{"error": "command_timeout"}'
        except Exception as e:
            return f'{{"error": "{e}"}}'

    def install_apk(self, apk_path: str) -> bool:
        """Install an APK on the Android device."""
        if not self.is_connected():
            return False
        try:
            result = subprocess.run(
                ['adb', '-s', self.device_id, 'install', '-r', apk_path],
                capture_output=True, text=True, timeout=60
            )
            return 'Success' in result.stdout
        except Exception:
            return False

    def push_file(self, local_path: str, remote_path: str) -> bool:
        """Push a file from PC to Android device."""
        if not self.is_connected():
            return False
        try:
            result = subprocess.run(
                ['adb', '-s', self.device_id, 'push', local_path, remote_path],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from Android device to PC."""
        if not self.is_connected():
            return False
        try:
            result = subprocess.run(
                ['adb', '-s', self.device_id, 'pull', remote_path, local_path],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_jarvis_app(self, package: str = 'com.jarvis.companion') -> bool:
        """Start the JARVIS Android companion app."""
        return 'Starting' in self.send_command(f'am start -n {package}/.MainActivity')

    def take_screenshot(self, save_path: str = '/sdcard/screenshot.png') -> bool:
        """Take screenshot on Android device."""
        if not self.is_connected():
            return False
        try:
            subprocess.run(
                ['adb', '-s', self.device_id, 'shell', 'screencap', '-p', save_path],
                capture_output=True, timeout=10
            )
            return True
        except Exception:
            return False

    def tap(self, x: int, y: int) -> str:
        """Simulate screen tap at coordinates."""
        return self.send_command(f'input tap {x} {y}')

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> str:
        """Simulate swipe gesture."""
        return self.send_command(f'input swipe {x1} {y1} {x2} {y2} {duration}')

    def type_text(self, text: str) -> str:
        """Type text on the Android device."""
        escaped = text.replace(' ', '%s').replace("'", "\\'")
        return self.send_command(f'input text "{escaped}"')

    def get_running_apps(self) -> List[str]:
        """Get list of recently running apps."""
        output = self.send_command('dumpsys activity activities | grep mResumedActivity')
        apps = []
        for line in output.split('\n'):
            if 'activity' in line and '/' in line:
                parts = line.split('/')
                if len(parts) >= 2:
                    pkg = parts[0].split()[-1]
                    if pkg and '.' in pkg:
                        apps.append(pkg)
        return list(set(apps))


# Singleton instance
_bridge: Optional[ADBBridge] = None


def get_adb_bridge(device_id: Optional[str] = None) -> ADBBridge:
    """Get singleton ADB bridge instance."""
    global _bridge
    if _bridge is None or device_id is not None:
        _bridge = ADBBridge(device_id)
    return _bridge


def is_android_connected() -> bool:
    """Quick check if any Android device is connected via ADB."""
    return get_adb_bridge().is_available()
