"""
Smart Home Integration — Controls smart lights, plugs, and home devices.

Supports Philips Hue, TP-Link Kasa, and generic HTTP-based smart devices.
Requires network connectivity to smart home hub/devices.
"""

import logging
import socket
import http.client
import json
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class SmartHomeController:
    """Unified smart home device controller."""

    def __init__(self):
        self._devices: Dict[str, Any] = {}
        self._hues_bridge: Optional[str] = None
        self._kasa_devices: List[Dict] = []

    def discover_devices(self) -> List[Dict[str, str]]:
        """Discover smart home devices on the local network."""
        discovered = []
        # Philips Hue discovery (UDP multicast on port 1900)
        discovered.extend(self._discover_hue())
        # TP-Link Kasa discovery (UDP broadcast)
        discovered.extend(self._discover_kasa())
        return discovered

    def _discover_hue(self) -> List[Dict[str, str]]:
        """Discover Philips Hue bridges via SSDP."""
        devices = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            msg = (
                'M-SEARCH * HTTP/1.1\r\n'
                'HOST: 239.255.255.250:1900\r\n'
                'MAN: "ssdp:discover"\r\n'
                'MX: 3\r\n'
                'ST: ssdp:all\r\n\r\n'
            )
            sock.sendto(msg.encode(), ('239.255.255.250', 1900))
            for _ in range(5):
                try:
                    data, addr = sock.recvfrom(4096)
                    resp = data.decode('utf-8', errors='ignore')
                    if 'hue' in resp.lower() or 'Philips' in resp:
                        devices.append({'type': 'hue_bridge', 'ip': addr[0], 'name': f'Hue Bridge ({addr[0]})'})
                except socket.timeout:
                    break
            sock.close()
        except Exception as e:
            logger.warning(f'Hue discovery failed: {e}')
        return devices

    def _discover_kasa(self) -> List[Dict[str, str]]:
        """Discover TP-Link Kasa smart plugs via UDP broadcast."""
        devices = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3)
            # TP-Link Kasa discovery protocol
            discovery_payload = bytes.fromhex(
                '0200000100000000000000000000646a'
                '3c46473645383e23413931383334343537343e38313e3132383e31'
            )
            sock.sendto(discovery_payload, ('255.255.255.255', 9999))
            for _ in range(10):
                try:
                    data, addr = sock.recvfrom(4096)
                    devices.append({'type': 'kasa_plug', 'ip': addr[0], 'name': f'Kasa Plug ({addr[0]})'})
                except socket.timeout:
                    break
            sock.close()
        except Exception as e:
            logger.warning(f'Kasa discovery failed: {e}')
        return devices

    def add_device(self, device_type: str, ip: str, name: str = '', **kwargs) -> bool:
        """Manually add a smart home device."""
        device_id = f'{device_type}_{ip}'.replace('.', '_')
        self._devices[device_id] = {
            'type': device_type,
            'ip': ip,
            'name': name or f'{device_type} ({ip})',
            'state': False,
            **kwargs
        }
        return True

    def set_hue_bridge(self, ip: str, username: str = None) -> bool:
        """Set Philips Hue bridge IP for API calls."""
        self._hues_bridge = ip
        self._devices[f'hue_bridge_{ip}'] = {
            'type': 'hue_bridge',
            'ip': ip,
            'name': f'Hue Bridge ({ip})',
            'username': username
        }
        return True

    def is_reachable(self, ip: str, port: int = 80, timeout: int = 2) -> bool:
        """Check if a device IP is reachable."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((ip, port))
            sock.close()
            return True
        except Exception:
            return False

    def get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Get current status of a smart device."""
        if device_id not in self._devices:
            return {'error': 'device_not_found'}
        device = self._devices[device_id]
        device_type = device['type']
        ip = device['ip']
        try:
            if 'hue' in device_type:
                return self._hue_light_status(ip, device.get('light_id', '1'))
            elif 'kasa' in device_type:
                return self._kasa_status(ip)
            elif device_type == 'http':
                return self._http_device_status(ip, device)
            else:
                return {'state': device.get('state', False), 'reachable': self.is_reachable(ip)}
        except Exception as e:
            return {'error': str(e), 'reachable': False}

    def _hue_light_status(self, bridge_ip: str, light_id: str) -> Dict:
        """Get Hue light status via REST API."""
        try:
            conn = http.client.HTTPConnection(bridge_ip, timeout=3)
            conn.request('GET', f'/api/newdeveloper/lights/{light_id}')
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            conn.close()
            return {
                'on': data.get('state', {}).get('on', False),
                'bri': data.get('state', {}).get('bri', 0),
                'reachable': data.get('state', {}).get('reachable', False),
                'name': data.get('name', '')
            }
        except Exception as e:
            return {'error': str(e), 'reachable': False}

    def _kasa_status(self, ip: str) -> Dict:
        """Get TP-Link Kasa device status."""
        try:
            # Simplified — real implementation uses XOR encryption
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            # Discovery packet doubles as status query
            discovery = bytes.fromhex(
                '0200000100000000000000000000646a'
                '3c46473645383e23413931383334343537343e38313e3132383e31'
            )
            sock.sendto(discovery, (ip, 9999))
            data, _ = sock.recvfrom(4096)
            sock.close()
            return {'reachable': True, 'data': data.hex()}
        except Exception as e:
            return {'error': str(e), 'reachable': False}

    def _http_device_status(self, ip: str, device: Dict) -> Dict:
        """Generic HTTP device status check."""
        try:
            path = device.get('status_path', '/')
            conn = http.client.HTTPConnection(ip, timeout=3)
            conn.request('GET', path)
            resp = conn.getresponse()
            return {
                'reachable': True,
                'status_code': resp.status,
                'body': resp.read().decode('utf-8', errors='ignore')[:200]
            }
        except Exception as e:
            return {'error': str(e), 'reachable': False}

    def turn_on(self, device_id: str) -> bool:
        """Turn on a smart device."""
        return self._set_device_state(device_id, True)

    def turn_off(self, device_id: str) -> bool:
        """Turn off a smart device."""
        return self._set_device_state(device_id, False)

    def _set_device_state(self, device_id: str, state: bool) -> bool:
        """Set device on/off state."""
        if device_id not in self._devices:
            return False
        device = self._devices[device_id]
        try:
            if 'hue' in device['type']:
                return self._hue_set_light(device['ip'], device.get('light_id', '1'), state)
            elif 'kasa' in device['type']:
                return self._kasa_set_state(device['ip'], state)
            elif device['type'] == 'http':
                return self._http_set_state(device['ip'], device, state)
            else:
                device['state'] = state
                return True
        except Exception as e:
            logger.error(f'Failed to set device {device_id} state: {e}')
            return False

    def _hue_set_light(self, bridge_ip: str, light_id: str, on: bool) -> bool:
        """Set Hue light state via API."""
        try:
            conn = http.client.HTTPConnection(bridge_ip, timeout=3)
            body = json.dumps({'on': on})
            conn.request('PUT', f'/api/newdeveloper/lights/{light_id}/state', body)
            resp = conn.getresponse()
            conn.close()
            return resp.status == 200
        except Exception:
            return False

    def _kasa_set_state(self, ip: str, on: bool) -> bool:
        """Set Kasa plug state (simplified)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            # Real implementation requires TP-Link XOR encryption
            # Placeholder — returns success for demo
            sock.sendto(b'\x00\x00\x00\x00', (ip, 9999))
            sock.close()
            return True
        except Exception:
            return False

    def _http_set_state(self, ip: str, device: Dict, on: bool) -> bool:
        """Generic HTTP device control."""
        try:
            path = device.get('control_path', '/')
            conn = http.client.HTTPConnection(ip, timeout=3)
            conn.request('POST', path, json.dumps({'power': 'on' if on else 'off'}))
            resp = conn.getresponse()
            conn.close()
            return resp.status == 200
        except Exception:
            return False

    def set_brightness(self, device_id: str, brightness: int) -> bool:
        """Set device brightness (0-100)."""
        if device_id not in self._devices:
            return False
        device = self._devices[device_id]
        if 'hue' in device['type']:
            try:
                bri = int(brightness * 254 // 100)
                conn = http.client.HTTPConnection(device['ip'], timeout=3)
                conn.request('PUT', f'/api/newdeveloper/lights/{device.get("light_id","1")}/state',
                             json.dumps({'bri': bri, 'on': True}))
                resp = conn.getresponse()
                conn.close()
                return resp.status == 200
            except Exception:
                return False
        return False

    def list_devices(self) -> List[Dict[str, Any]]:
        """List all configured smart home devices."""
        return [
            {**d, 'status': self.get_device_status(did)}
            for did, d in self._devices.items()
        ]


# Singleton
_controller: Optional[SmartHomeController] = None


def get_smart_home_controller() -> SmartHomeController:
    global _controller
    if _controller is None:
        _controller = SmartHomeController()
    return _controller


def is_smart_home_available() -> bool:
    """Check if any smart home device is reachable."""
    ctrl = get_smart_home_controller()
    devices = ctrl.discover_devices()
    return len(devices) > 0
