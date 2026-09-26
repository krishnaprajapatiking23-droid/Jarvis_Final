"""Live host telemetry for the dashboard (deep-spec section 9).

Every number here is measured from the running machine. When a metric cannot
be read the reader returns UNAVAILABLE with the reason instead of inventing a
placeholder, because a dashboard that lies is worse than one that is blank.
"""

import os
import platform
import shutil
import socket
import sys
import time
from typing import Any, Dict, List, Optional

OK = "ok"
UNAVAILABLE = "UNAVAILABLE"

HISTORY_SIZE = 120
MIN_CPU_INTERVAL = 0.05


def _metric(name: str, value: Any, unit: str = "%", **extra: Any) -> Dict[str, Any]:
    out = {"metric": name, "status": OK, "value": value, "unit": unit,
           "reason": None, "at": time.time()}
    out.update(extra)
    return out


def _unavailable(name: str, reason: str, unit: str = "%") -> Dict[str, Any]:
    return {"metric": name, "status": UNAVAILABLE, "value": None, "unit": unit,
            "reason": reason, "at": time.time()}


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r") as handle:
            return handle.read()
    except Exception:
        return None


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total <= 0:
        return "0h 00m 00s"
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return "%dd %02dh %02dm %02ds" % (days, hours, minutes, secs)
    return "%dh %02dm %02ds" % (hours, minutes, secs)


class CpuSampler:
    """CPU load from /proc/stat deltas.

    A single reading of the counters cannot produce a percentage, so the first
    sample says so rather than reporting a meaningless number.
    """

    def __init__(self, stat_path: str = "/proc/stat") -> None:
        self.stat_path = stat_path
        self._previous: Optional[Any] = None
        self._previous_at = 0.0

    def _counters(self) -> Optional[Any]:
        raw = _read(self.stat_path)
        if not raw:
            return None
        for line in raw.splitlines():
            if line.startswith("cpu "):
                fields = [float(v) for v in line.split()[1:] if v.strip()]
                if len(fields) < 4:
                    return None
                idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
                return (sum(fields), idle)
        return None

    def sample(self) -> Dict[str, Any]:
        counters = self._counters()
        if counters is None:
            return _unavailable("cpu", "cpu counters unreadable at %s"
                                % self.stat_path)
        now = time.time()
        previous = self._previous
        self._previous = counters
        self._previous_at = now
        if previous is None:
            return _unavailable("cpu", "first sample: no interval to compare yet")
        total_delta = counters[0] - previous[0]
        idle_delta = counters[1] - previous[1]
        if total_delta <= 0:
            return _unavailable("cpu", "no measurable interval between samples")
        used = (total_delta - idle_delta) / total_delta * 100.0
        used = max(0.0, min(100.0, used))
        return _metric("cpu", round(used, 1))


def memory() -> Dict[str, Any]:
    raw = _read("/proc/meminfo")
    if raw:
        fields = {}
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                try:
                    fields[parts[0].strip()] = float(parts[1].split()[0])
                except Exception:
                    continue
        total = fields.get("MemTotal")
        if total:
            available = fields.get("MemAvailable")
            if available is None:
                available = (fields.get("MemFree", 0.0)
                             + fields.get("Cached", 0.0)
                             + fields.get("Buffers", 0.0))
            used = max(0.0, total - available)
            return _metric("memory", round(used / total * 100.0, 1),
                           total_gb=round(total / 1048576.0, 2),
                           used_gb=round(used / 1048576.0, 2))
    try:  # non-Linux fallback
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        return _metric("memory", round(vm.percent, 1),
                       total_gb=round(vm.total / 1073741824.0, 2),
                       used_gb=round((vm.total - vm.available) / 1073741824.0, 2))
    except Exception as exc:
        return _unavailable("memory", "memory counters unreadable: %s" % exc)


def storage(path: str = "/") -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except Exception as exc:
        return _unavailable("storage", "cannot read %s: %s" % (path, exc))
    if usage.total <= 0:
        return _unavailable("storage", "mount %s reports zero capacity" % path)
    gb = 1073741824.0
    return _metric("storage", round(usage.used / usage.total * 100.0, 1),
                   mount=path,
                   total_gb=round(usage.total / gb, 2),
                   used_gb=round(usage.used / gb, 2),
                   free_gb=round(usage.free / gb, 2))


def battery(power_root: str = "/sys/class/power_supply") -> Dict[str, Any]:
    try:
        names = sorted(os.listdir(power_root))
    except Exception:
        names = []
    for name in names:
        node = os.path.join(power_root, name)
        kind = (_read(os.path.join(node, "type")) or "").strip().lower()
        if kind != "battery":
            continue
        capacity = (_read(os.path.join(node, "capacity")) or "").strip()
        if not capacity:
            continue
        try:
            level = int(float(capacity))
        except Exception:
            continue
        state = (_read(os.path.join(node, "status")) or "unknown").strip().lower()
        return _metric("battery", level, state=state, source=name)
    return _unavailable("battery", "no battery present on this machine")


def network(host: str = "127.0.0.1", port: int = 80,
            timeout: float = 1.0) -> Dict[str, Any]:
    local_ip = None
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:  # does not send traffic; just asks the routing table
        probe.connect(("203.0.113.1", 9))
        local_ip = probe.getsockname()[0]
    except Exception:
        local_ip = None
    finally:
        probe.close()
    started = time.time()
    try:
        connection = socket.create_connection((host, int(port)), timeout)
        connection.close()
    except Exception as exc:
        return {"metric": "network", "status": UNAVAILABLE, "value": None,
                "unit": "ms", "local_ip": local_ip,
                "reason": "probe to %s:%s failed: %s" % (host, port, exc),
                "at": time.time()}
    latency = (time.time() - started) * 1000.0
    return _metric("network", round(latency, 1), unit="ms",
                   local_ip=local_ip, target="%s:%s" % (host, port))


def uptime() -> Dict[str, Any]:
    raw = _read("/proc/uptime")
    if raw:
        try:
            seconds = float(raw.split()[0])
            return _metric("uptime", round(seconds, 1), unit="s",
                           pretty=format_duration(seconds))
        except Exception:
            pass
    try:
        seconds = time.time() - os.path.getmtime("/proc/1")
        return _metric("uptime", round(seconds, 1), unit="s",
                       pretty=format_duration(seconds))
    except Exception as exc:
        return _unavailable("uptime", "host uptime unreadable: %s" % exc,
                            unit="s")


def host_info() -> Dict[str, Any]:
    try:
        cores = os.cpu_count() or 1
    except Exception:
        cores = 1
    mem = memory()
    disk = storage("/")
    return {"os": "%s %s" % (platform.system() or "unknown",
                             platform.release() or ""),
            "machine": platform.machine() or "unknown",
            "processor": platform.processor() or platform.machine() or "unknown",
            "hostname": socket.gethostname(),
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "cores": int(cores),
            "memory_gb": mem.get("total_gb"),
            "storage_gb": disk.get("total_gb")}


class TelemetryProvider:
    """Samples every dashboard metric, keeping a bounded history for trends."""

    capability = "ui_telemetry"

    METRICS = ("cpu", "memory", "storage", "battery", "network", "uptime")

    def __init__(self, probe_host: str = "127.0.0.1", probe_port: int = 80,
                 history_size: int = HISTORY_SIZE, mount: str = "/",
                 power_root: str = "/sys/class/power_supply") -> None:
        self.probe_host = probe_host
        self.probe_port = probe_port
        self.history_size = max(2, int(history_size))
        self.mount = mount
        self.power_root = power_root
        self._cpu = CpuSampler()
        self.history: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in self.METRICS}
        self.samples = 0
        self.started = time.time()

    def sample(self) -> Dict[str, Any]:
        readers = {
            "cpu": self._cpu.sample,
            "memory": memory,
            "storage": lambda: storage(self.mount),
            "battery": lambda: battery(self.power_root),
            "network": lambda: network(self.probe_host, self.probe_port, 1.0),
            "uptime": uptime,
        }
        metrics: Dict[str, Any] = {}
        degraded: List[str] = []
        for name, reader in readers.items():
            try:
                value = reader()
            except Exception as exc:  # a reader must never take the UI down
                value = _unavailable(name, "reader failed: %s" % exc)
            metrics[name] = value
            if value.get("status") != OK:
                degraded.append(name)
            series = self.history.setdefault(name, [])
            series.append(value)
            if len(series) > self.history_size:
                del series[0:len(series) - self.history_size]
        self.samples += 1
        return {"status": OK, "at": time.time(), "metrics": metrics,
                "degraded": sorted(degraded), "sample": self.samples,
                "session_uptime": format_duration(time.time() - self.started)}

    def trend(self, name: str, window: int = 5) -> Optional[float]:
        """Change between the oldest and newest OK reading in the window."""
        series = [entry for entry in self.history.get(name, [])
                  if entry.get("status") == OK
                  and isinstance(entry.get("value"), (int, float))]
        series = series[-int(max(2, window)):]
        if len(series) < 2:
            return None
        return round(float(series[-1]["value"]) - float(series[0]["value"]), 2)

    def health(self) -> Dict[str, Any]:
        latest = {name: (series[-1]["status"] if series else UNAVAILABLE)
                  for name, series in self.history.items()}
        return {"available": True, "status": OK, "samples": self.samples,
                "metrics": latest,
                "degraded": sorted(n for n, s in latest.items() if s != OK),
                "history_size": self.history_size}
