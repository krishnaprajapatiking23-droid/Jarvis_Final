"""
Home Page — Real system stats, capability overview, and quick actions.
"""
import tkinter as tk
from tkinter import scrolledtext
import threading
import platform
import psutil
import time
import os

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HomePage(tk.Frame):
    """Real-time dashboard showing Jarvis state and system metrics."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._refresh_job = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI Layout                                                          #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#1E1E1E")
        header.pack(fill="x", padx=20, pady=(20, 0))

        tk.Label(
            header, text="JARVIS AI", bg="#1E1E1E", fg="#00BCD4",
            font=("Arial", 18, "bold")
        ).pack(side="left")

        self._version_label = tk.Label(
            header, text="v1.0.0 PRO", bg="#1E1E1E", fg="#81C784",
            font=("Arial", 10)
        )
        self._version_label.pack(side="left", padx=(8, 0))

        self._uptime_label = tk.Label(
            header, text="", bg="#1E1E1E", fg="#888",
            font=("Arial", 9)
        )
        self._uptime_label.pack(side="right")

        # Status row
        status_frame = tk.Frame(self, bg="#252526", bd=1, relief="solid")
        status_frame.pack(fill="x", padx=20, pady=(15, 0))

        self._status_indicators = {}
        for i, (key, label_text) in enumerate([
            ("jarvis", "JARVIS"), ("brain", "BRAIN"), ("voice", "VOICE"),
            ("vision", "VISION"), ("memory", "MEMORY"),
        ]):
            col = i % 5
            lbl = tk.Label(
                status_frame, text=f"● {label_text}",
                bg="#252526", fg="#4CAF50",
                font=("Arial", 9, "bold")
            )
            lbl.pack(side="left", padx=12, pady=8)
            self._status_indicators[key] = lbl

        # Two-column layout
        cols = tk.Frame(self, bg="#1E1E1E")
        cols.pack(fill="both", expand=True, padx=20, pady=15)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        # Left column: System Info
        left = tk.Frame(cols, bg="#1E1E1E")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self._sys_frame = tk.LabelFrame(
            left, text="System Overview", bg="#252526", fg="#00BCD4",
            font=("Arial", 11, "bold"), padx=12, pady=10
        )
        self._sys_frame.pack(fill="both", expand=True)

        # Right column: Capabilities
        right = tk.Frame(cols, bg="#1E1E1E")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        cap_frame = tk.LabelFrame(
            right, text="Jarvis Capabilities", bg="#252526", fg="#00BCD4",
            font=("Arial", 11, "bold"), padx=12, pady=10
        )
        cap_frame.pack(fill="both", expand=True)

        self._cap_labels = {}
        self._build_capabilities(cap_frame)

        # Quick Actions bar
        actions_frame = tk.LabelFrame(
            self, text="Quick Actions", bg="#252526", fg="#00BCD4",
            font=("Arial", 11, "bold"), padx=12, pady=10
        )
        actions_frame.pack(fill="x", padx=20, pady=(0, 10))

        quick_actions = [
            ("📝 Notepad", "open notepad"),
            ("🧮 Calculator", "open calculator"),
            ("🌐 Browser", "open browser"),
            ("📁 Explorer", "open file explorer"),
            ("📸 Screenshot", "take screenshot"),
            ("🔄 Health Check", "run diagnostics"),
            ("⏰ Reminders", "show reminders"),
            ("🔔 Check Updates", "check for updates"),
        ]
        for i, (label_text, cmd) in enumerate(quick_actions):
            btn = tk.Button(
                actions_frame, text=label_text,
                command=lambda c=cmd: self._do_action(c),
                bg="#37474F", fg="white", font=("Arial", 9),
                width=14, cursor="hand2", relief="flat"
            )
            btn.grid(row=i // 4, column=i % 4, padx=4, pady=4, sticky="ew")
        for c in range(4):
            actions_frame.columnconfigure(c, weight=1)

        self._update_system_info()
        self._start_refresh()

    def _build_capabilities(self, parent):
        try:
            import sys
            sys.path.insert(0, JARVIS_ROOT)
            from jarvis_core.capability_registry import get_capability_registry
            reg = get_capability_registry()
            caps = reg.all()
        except Exception:
            caps = {}

        self._cap_labels = {}
        for cap in caps:
            row = tk.Frame(parent, bg="#252526")
            row.pack(fill="x", pady=1)
            name_lbl = tk.Label(
                row, text=cap.label,
                bg="#252526", fg="#ccc", font=("Arial", 9)
            )
            name_lbl.pack(side="left")
            status = cap.state.value
            color = self._status_color(status)
            status_lbl = tk.Label(
                row, text=f"● {status}",
                bg="#252526", fg=color, font=("Arial", 9, "bold")
            )
            status_lbl.pack(side="right")
            self._cap_labels[cap.id] = (name_lbl, status_lbl)

    # ------------------------------------------------------------------ #
    #  System Stats                                                       #
    # ------------------------------------------------------------------ #
    def _update_system_info(self):
        for widget in self._sys_frame.winfo_children():
            widget.destroy()

        stats = self._collect_stats()

        rows = [
            ("OS", stats.get("os", "?")),
            ("CPU", stats.get("cpu", "?")),
            ("RAM", stats.get("ram", "?")),
            ("Storage (C:)", stats.get("storage", "?")),
            ("GPU", stats.get("gpu", "?")),
            ("Network", stats.get("network", "?")),
            ("Battery", stats.get("battery", "N/A")),
        ]
        for label_text, value_text in rows:
            row = tk.Frame(self._sys_frame, bg="#252526")
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=f"{label_text}:", bg="#252526", fg="#888",
                font=("Arial", 9), width=14, anchor="w"
            ).pack(side="left")
            tk.Label(
                row, text=value_text, bg="#252526", fg="white",
                font=("Arial", 9, "bold")
            ).pack(side="left")

        # Health bar
        health_row = tk.Frame(self._sys_frame, bg="#252526")
        health_row.pack(fill="x", pady=(6, 0))
        tk.Label(
            health_row, text="System Health:", bg="#252526", fg="#888",
            font=("Arial", 9)
        ).pack(side="left")
        self._health_bar = tk.Frame(health_row, bg="#4CAF50", width=120, height=14)
        self._health_bar.pack(side="left", padx=(4, 0))
        self._health_bar.pack_propagate(False)

        # Jarvis status
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from jarvis_core.capability_registry import get_capability_registry
            reg = get_capability_registry()
            summary = reg.jarvis_status()
            self._status_indicators["jarvis"].config(
                fg=self._status_color(summary.get("overall", "UNKNOWN"))
            )
        except Exception:
            pass

    def _collect_stats(self) -> dict:
        try:
            boot = psutil.boot_time()
            uptime_s = time.time() - boot
            hours, rem = divmod(int(uptime_s), 3600)
            mins = rem // 60
            uptime_str = f"{hours}h {mins}m"
            self._uptime_label.config(text=f"Uptime: {uptime_str}")
        except Exception:
            uptime_str = "?"

        try:
            cpu_pct = psutil.cpu_percent(interval=0.1)
            cpu_str = f"{psutil.cpu_count()} cores — {cpu_pct:.0f}%"
        except Exception:
            cpu_str = "?"

        try:
            mem = psutil.virtual_memory()
            ram_str = f"{mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB ({mem.percent:.0f}%)"
        except Exception:
            ram_str = "?"

        try:
            disk = psutil.disk_usage("C:\\")
            storage_str = f"{disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent:.0f}%)"
        except Exception:
            storage_str = "?"

        try:
            battery = psutil.sensors_battery()
            if battery:
                plugged = "Plugged In" if battery.power_plugged else "On Battery"
                batt_str = f"{battery.percent:.0f}% — {plugged}"
            else:
                batt_str = "N/A (Desktop)"
        except Exception:
            batt_str = "N/A"

        try:
            net = psutil.net_io_counters()
            sent_mb = net.bytes_sent // (1024 * 1024)
            recv_mb = net.bytes_recv // (1024 * 1024)
            net_str = f"↑{sent_mb}MB ↓{recv_mb}MB"
        except Exception:
            net_str = "?"

        return {
            "os": f"{platform.system()} {platform.release()}",
            "cpu": cpu_str,
            "ram": ram_str,
            "storage": storage_str,
            "gpu": self._get_gpu(),
            "network": net_str,
            "battery": batt_str,
        }

    @staticmethod
    def _get_gpu() -> str:
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=3
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            if len(lines) >= 2:
                return lines[1][:50]
        except Exception:
            pass
        return "Unknown"

    # ------------------------------------------------------------------ #
    #  Capability refresh                                                 #
    # ------------------------------------------------------------------ #
    def _refresh_capabilities(self):
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from jarvis_core.capability_registry import get_capability_registry
            reg = get_capability_registry()
            caps = reg.all()
            for cap in caps:
                if cap.id in self._cap_labels:
                    _, status_lbl = self._cap_labels[cap.id]
                    status = cap.state.value
                    status_lbl.config(
                        text=f"● {status}",
                        fg=self._status_color(status)
                    )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Refresh loop                                                       #
    # ------------------------------------------------------------------ #
    def _start_refresh(self):
        self._do_refresh()
        self._refresh_job = self.after(5000, self._start_refresh)

    def _do_refresh(self):
        self._update_system_info()
        self._refresh_capabilities()

    def stop_refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)

    # ------------------------------------------------------------------ #
    #  Quick actions                                                       #
    # ------------------------------------------------------------------ #
    def _do_action(self, command: str):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from core.router import route_command
                from conversation.identity import identity
                route_command(command, identity.owner())
            except Exception as e:
                print(f"[HomePage Action] Error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _status_color(status: str) -> str:
        colors = {
            "AVAILABLE": "#4CAF50",
            "DEGRADED": "#FFC107",
            "NOT_CONFIGURED": "#FF9800",
            "UNAVAILABLE": "#F44336",
            "ERROR": "#F44336",
            "DISABLED": "#9E9E9E",
        }
        return colors.get(status.upper(), "#888")
