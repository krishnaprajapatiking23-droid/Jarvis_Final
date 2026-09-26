"""
Smart Home Manager — controls IoT and smart home devices.

Supported integrations:
  - Philips Hue (via phue library)
  - Generic HTTP-based smart plugs/switches
  - Shell commands for local scripts (e.g. Home Assistant REST API)

Install optional deps:
    pip install phue  # Philips Hue
"""

import json
import subprocess
import urllib.request
from threading import Lock
from typing import Dict, List, Optional


class SmartHomeManager:

    def __init__(self):
        self._devices: Dict[str, Dict] = {}
        self._locks: Dict[str, Lock] = {}
        self._hue_bridge: Optional[str] = None

    # ------------------------------------------------------------------
    # Device registration
    # ------------------------------------------------------------------

    def register_light(self, name: str, host: str = None,
                       light_id: int = None) -> Dict:
        """Register a smart light (Hue or HTTP-based)."""
        dev = {"name": name, "type": "light", "host": host,
               "light_id": light_id, "state": "unknown"}
        self._devices[name] = dev
        self._locks[name] = Lock()
        return {"success": True, "registered": name}

    def register_plug(self, name: str, host: str,
                     port: int = 80) -> Dict:
        """Register an HTTP-controlled smart plug."""
        dev = {"name": name, "type": "plug", "host": host, "port": port,
               "state": "unknown"}
        self._devices[name] = dev
        self._locks[name] = Lock()
        return {"success": True, "registered": name}

    def unregister(self, name: str) -> Dict:
        """Remove a device."""
        if name in self._devices:
            del self._devices[name]
            self._locks.pop(name, None)
            return {"success": True, "unregistered": name}
        return {"success": False, "error": f"Device '{name}' not found"}

    # ------------------------------------------------------------------
    # Light control
    # ------------------------------------------------------------------

    def set_light(self, name: str, on: bool = True,
                  brightness: int = None) -> Dict:
        """Turn a light on/off and optionally set brightness (0-254)."""
        if name not in self._devices:
            return {"success": False, "error": "Unknown device"}

        dev = self._devices[name]
        with self._locks[name]:
            if dev["type"] == "light" and dev.get("light_id") is not None:
                return self._hue_light(dev["light_id"], on, brightness)
            elif dev["type"] == "light" and dev.get("host"):
                return self._http_light(dev["host"], on, brightness)
            return {"success": False, "error": "Light not configured"}

    def _hue_light(self, light_id: int, on: bool,
                   brightness: int = None) -> Dict:
        try:
            from phue import Bridge
            if self._hue_bridge is None:
                return {"success": False,
                        "error": "Hue bridge not set — call set_hue_bridge()"}
            b = Bridge(self._hue_bridge)
            b.connect()
            cmd = {"on": on}
            if brightness is not None:
                cmd["bri"] = max(1, min(254, brightness))
            b.set_light(light_id, cmd)
            return {"success": True, "light_id": light_id, "state": "on" if on else "off"}
        except ImportError:
            return {"success": False, "error": "phue not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _http_light(self, host: str, on: bool,
                    brightness: int = None) -> Dict:
        try:
            state = "ON" if on else "OFF"
            url = f"http://{host}/set?state={state}"
            if brightness is not None:
                url += f"&brightness={brightness}"
            urllib.request.urlopen(url, timeout=5)
            return {"success": True, "host": host, "state": state}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_hue_bridge(self, ip: str) -> Dict:
        """Set the Philips Hue bridge IP for subsequent calls."""
        self._hue_bridge = ip
        return {"success": True, "bridge_ip": ip}

    # ------------------------------------------------------------------
    # Generic plug control
    # ------------------------------------------------------------------

    def plug_on(self, name: str) -> Dict:
        """Turn a smart plug on."""
        if name not in self._devices:
            return {"success": False, "error": "Unknown device"}
        dev = self._devices[name]
        if dev["type"] != "plug":
            return {"success": False, "error": "Not a plug"}
        with self._locks[name]:
            return self._http_set_plug(dev["host"], dev.get("port", 80), True)

    def plug_off(self, name: str) -> Dict:
        """Turn a smart plug off."""
        if name not in self._devices:
            return {"success": False, "error": "Unknown device"}
        dev = self._devices[name]
        if dev["type"] != "plug":
            return {"success": False, "error": "Not a plug"}
        with self._locks[name]:
            return self._http_set_plug(dev["host"], dev.get("port", 80), False)

    def _http_set_plug(self, host: str, port: int, on: bool) -> Dict:
        state = "ON" if on else "OFF"
        try:
            urllib.request.urlopen(
                f"http://{host}:{port}/set?state={state}", timeout=5)
            return {"success": True, "host": host, "state": state}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def scene(self, name: str) -> Dict:
        """Activate a named scene (lights preset)."""
        devices = list(self._devices.keys())
        scenes = {
            "movie":   lambda d=devices: [self.set_light(l, True, 50) for l in d],
            "morning": lambda d=devices: [self.set_light(l, True, 200) for l in d],
            "off":     lambda d=devices: [self.set_light(l, False) for l in d],
        }
        if name not in scenes:
            return {"success": False, "error": f"Scene '{name}' not defined"}
        scenes[name]()
        return {"success": True, "scene": name}

    def all_off(self) -> Dict:
        """Turn off all registered devices."""
        results = []
        for name in self._devices:
            res = self.plug_off(name) if self._devices[name]["type"] == "plug" \
                else self.set_light(name, False)
            results.append(res)
        return {"success": True, "devices_affected": len(results)}

    def list_devices(self) -> List[Dict]:
        return list(self._devices.values())


_manager = SmartHomeManager()

register_light = _manager.register_light
register_plug = _manager.register_plug
unregister = _manager.unregister
set_light = _manager.set_light
plug_on = _manager.plug_on
plug_off = _manager.plug_off
scene = _manager.scene
all_off = _manager.all_off
list_devices = _manager.list_devices
set_hue_bridge = _manager.set_hue_bridge
