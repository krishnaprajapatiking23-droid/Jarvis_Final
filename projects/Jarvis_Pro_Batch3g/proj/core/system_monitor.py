"""
==========================================
JARVIS PRO
System monitor & proactive alerts
==========================================

Roadmap sections 12 (computer automation: system info) and 17/23
(background intelligence, proactive alerts).

Adapted from ULTRON ``actions/system_monitor.py`` and the Mark-LII
background monitor, with every heavy dependency imported lazily so that
importing this module never fails - if ``psutil`` or the NVIDIA bindings
are missing, the affected numbers are simply reported as unavailable.

Usage:

    from automation.system_monitor import monitor

    monitor.snapshot()      # raw numbers
    monitor.report()        # one spoken-style sentence
    monitor.alerts()        # only threshold breaches (cool-down aware)
    monitor.start()         # background watcher -> event bus
"""

from __future__ import annotations

import platform
import shutil
import threading
import time
from typing import Any, Callable

from config import config
from core.observability import observability


ALERT_COOLDOWN = 300.0
CPU_STREAK = 3


def _psutil() -> Any:
    try:
        import psutil

        return psutil

    except Exception:
        return None


class SystemMonitor:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_alert: dict[str, float] = {}
        self._cpu_hits = 0
        self._listeners: list[Callable[[dict], None]] = []

    # ---------------------------------------------------- thresholds

    def thresholds(self) -> dict[str, float]:
        return {
            "cpu": float(config.get("monitor.cpu", 90.0)),
            "ram": float(config.get("monitor.ram", 90.0)),
            "temp": float(config.get("monitor.temp", 85.0)),
            "gpu": float(config.get("monitor.gpu", 95.0)),
            "disk": float(config.get("monitor.disk", 92.0)),
            "battery": float(config.get("monitor.battery", 20.0)),
        }

    # ---------------------------------------------------- readings

    def _gpu(self) -> dict[str, Any]:
        try:
            import pynvml

            pynvml.nvmlInit()

            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            usage = pynvml.nvmlDeviceGetUtilizationRates(handle)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)

            name = pynvml.nvmlDeviceGetName(handle)

            if isinstance(name, bytes):
                name = name.decode("utf-8", "ignore")

            try:
                temperature = float(
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )

            except Exception:
                temperature = None

            result = {
                "available": True,
                "name": str(name),
                "usage": float(usage.gpu),
                "memory_percent": round(memory.used / memory.total * 100, 1)
                if memory.total
                else None,
                "temperature": temperature,
            }

            try:
                pynvml.nvmlShutdown()

            except Exception:
                pass

            return result

        except Exception:
            return {"available": False}

    def _temperature(self, psutil: Any) -> float | None:
        getter = getattr(psutil, "sensors_temperatures", None)

        if getter is None:
            return None

        try:
            readings = getter() or {}

        except Exception:
            return None

        values = [
            float(entry.current)
            for entries in readings.values()
            for entry in entries
            if getattr(entry, "current", None)
        ]

        return round(max(values), 1) if values else None

    def snapshot(self) -> dict[str, Any]:
        """Current machine state. Always returns a dict, never raises."""

        psutil = _psutil()

        data: dict[str, Any] = {
            "at": time.time(),
            "os": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "python": platform.python_version(),
            "psutil": psutil is not None,
        }

        if psutil is None:
            try:
                usage = shutil.disk_usage(str(config.path()))

                data["disk"] = {
                    "percent": round(usage.used / usage.total * 100, 1),
                    "free_gb": round(usage.free / 1024**3, 1),
                }

            except Exception:
                pass

            data["note"] = "install psutil for full telemetry"

            return data

        try:
            data["cpu"] = {
                "percent": float(psutil.cpu_percent(interval=0.3)),
                "cores": psutil.cpu_count(logical=True),
                "physical": psutil.cpu_count(logical=False),
            }

            memory = psutil.virtual_memory()

            data["ram"] = {
                "percent": float(memory.percent),
                "total_gb": round(memory.total / 1024**3, 1),
                "used_gb": round(memory.used / 1024**3, 1),
                "free_gb": round(memory.available / 1024**3, 1),
            }

            disk = psutil.disk_usage(str(config.path()))

            data["disk"] = {
                "percent": float(disk.percent),
                "total_gb": round(disk.total / 1024**3, 1),
                "free_gb": round(disk.free / 1024**3, 1),
            }

            data["temperature"] = self._temperature(psutil)
            data["uptime_hours"] = round(
                (time.time() - psutil.boot_time()) / 3600, 1
            )
            data["processes"] = len(psutil.pids())

            battery = getattr(psutil, "sensors_battery", lambda: None)()

            if battery is not None:
                data["battery"] = {
                    "percent": float(battery.percent),
                    "plugged": bool(battery.power_plugged),
                }

        except Exception as error:
            data["error"] = str(error)

        data["gpu"] = self._gpu()

        return data

    def top_processes(self, limit: int = 5) -> list[dict[str, Any]]:
        """Heaviest processes - used when explaining why the PC is slow."""

        psutil = _psutil()

        if psutil is None:
            return []

        items: list[dict[str, Any]] = []

        try:
            for process in psutil.process_iter(["pid", "name", "memory_percent"]):
                info = process.info

                items.append(
                    {
                        "pid": info.get("pid"),
                        "name": info.get("name") or "?",
                        "memory_percent": round(
                            float(info.get("memory_percent") or 0.0), 1
                        ),
                    }
                )

        except Exception:
            return items[:limit]

        items.sort(key=lambda item: item["memory_percent"], reverse=True)

        return items[:limit]

    # ---------------------------------------------------- reporting

    def report(self) -> str:
        """Short human sentence, ready for the voice layer."""

        data = self.snapshot()

        if not data.get("psutil"):
            return (
                "I can only read basic system information right now - "
                "install psutil for full telemetry."
            )

        parts = [
            f"CPU {data.get('cpu', {}).get('percent', 0):.0f}%",
            f"RAM {data.get('ram', {}).get('percent', 0):.0f}%",
            f"disk {data.get('disk', {}).get('percent', 0):.0f}% used",
        ]

        if data.get("temperature"):
            parts.append(f"{data['temperature']:.0f} degrees")

        gpu = data.get("gpu", {})

        if gpu.get("available"):
            parts.append(f"GPU {gpu.get('usage', 0):.0f}%")

        battery = data.get("battery")

        if battery:
            state = "charging" if battery["plugged"] else "on battery"
            parts.append(f"battery {battery['percent']:.0f}% ({state})")

        return ", ".join(parts) + "."

    # ---------------------------------------------------- alerts

    def _cooled_down(self, name: str) -> bool:
        now = time.time()

        with self._lock:
            if now - self._last_alert.get(name, 0.0) < ALERT_COOLDOWN:
                return False

            self._last_alert[name] = now

        return True

    def alerts(self, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Threshold breaches worth telling the user about."""

        data = data or self.snapshot()
        limits = self.thresholds()
        found: list[dict[str, Any]] = []

        cpu = float(data.get("cpu", {}).get("percent", 0.0) or 0.0)

        # CPU must stay high for several samples - avoids false alarms.
        if cpu >= limits["cpu"]:
            with self._lock:
                self._cpu_hits += 1
                hits = self._cpu_hits

            if hits >= CPU_STREAK and self._cooled_down("cpu"):
                found.append(
                    {
                        "kind": "cpu",
                        "severity": "high",
                        "value": cpu,
                        "message": f"CPU has been at {cpu:.0f}% for a while.",
                    }
                )
        else:
            with self._lock:
                self._cpu_hits = 0

        checks = [
            ("ram", float(data.get("ram", {}).get("percent", 0.0) or 0.0), limits["ram"], "Memory"),
            ("disk", float(data.get("disk", {}).get("percent", 0.0) or 0.0), limits["disk"], "Disk"),
            ("temp", float(data.get("temperature") or 0.0), limits["temp"], "Temperature"),
            (
                "gpu",
                float((data.get("gpu") or {}).get("usage") or 0.0),
                limits["gpu"],
                "GPU",
            ),
        ]

        for name, value, limit, label in checks:
            if value and value >= limit and self._cooled_down(name):
                found.append(
                    {
                        "kind": name,
                        "severity": "high",
                        "value": value,
                        "message": f"{label} is at {value:.0f}%."
                        if name != "temp"
                        else f"{label} reached {value:.0f} degrees.",
                    }
                )

        battery = data.get("battery")

        if (
            battery
            and not battery["plugged"]
            and battery["percent"] <= limits["battery"]
            and self._cooled_down("battery")
        ):
            found.append(
                {
                    "kind": "battery",
                    "severity": "medium",
                    "value": battery["percent"],
                    "message": f"Battery is down to {battery['percent']:.0f}%.",
                }
            )

        for alert in found:
            observability.warn("system_monitor", alert["message"], kind=alert["kind"])

        return found

    # ---------------------------------------------------- background

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        """Receive alerts (the voice layer or the HUD subscribes here)."""

        with self._lock:
            self._listeners.append(callback)

    def _publish(self, alert: dict[str, Any]) -> None:
        try:
            from core.event_bus import event_bus  # type: ignore

            publish = getattr(event_bus, "publish", None) or getattr(
                event_bus, "emit", None
            )

            if callable(publish):
                publish("system.alert", alert)

        except Exception:
            pass

        for callback in list(self._listeners):
            try:
                callback(alert)

            except Exception:
                continue

    def _loop(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                for alert in self.alerts():
                    self._publish(alert)

            except Exception as error:
                observability.warn("system_monitor", f"watcher error: {error}")

    def start(self, interval: float = 30.0) -> bool:
        """Start the background watcher (idempotent)."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                args=(max(interval, 5.0),),
                name="jarvis-system-monitor",
                daemon=True,
            )
            self._thread.start()

        observability.info("system_monitor", "watcher started", interval=interval)

        return True

    def stop(self) -> None:
        self._stop.set()

        with self._lock:
            self._thread = None

    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()


monitor = SystemMonitor()
