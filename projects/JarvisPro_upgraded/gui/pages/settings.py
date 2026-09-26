"""
Settings Page — Configuration, diagnostics, and updater management.
"""
import tkinter as tk
from tkinter import scrolledtext
import threading
import os
import platform

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
sys.path.insert(0, JARVIS_ROOT)
from updater.health_checker import HealthChecker


class SettingsPage(tk.Frame):
    """Settings, diagnostics, and system management backed by real subsystems."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._tabs = None
        self._diag_text = None
        self._update_text = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI Layout                                                          #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        title = tk.Label(
            self, text="Settings & System", bg="#1E1E1E", fg="#00BCD4",
            font=("Arial", 16, "bold")
        )
        title.pack(anchor="w", padx=20, pady=(15, 5))

        self._tabs = tk.ttk.Notebook(self) if hasattr(tk, "ttk") else tk.Frame(self, bg="#1E1E1E")
        if hasattr(self._tabs, "pack"):
            self._tabs.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        else:
            self._tabs.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self._build_diagnostics_tab()
        self._build_update_tab()
        self._build_config_tab()
        self._build_about_tab()

    def _tab_frame(self, text: str) -> tk.Frame:
        f = tk.Frame(self._tabs, bg="#252526")
        self._tabs.add(f, text=f"  {text}  ") if hasattr(self._tabs, "add") else f.pack(fill="both", expand=True)
        return f

    # ------------------------------------------------------------------ #
    #  Diagnostics Tab                                                     #
    # ------------------------------------------------------------------ #
    def _build_diagnostics_tab(self):
        frame = self._tab_frame("Diagnostics")

        tb = tk.Frame(frame, bg="#252526")
        tb.pack(fill="x", padx=10, pady=(10, 5))
        tk.Button(tb, text="🔍 Run Full Diagnostics", command=self._run_diagnostics,
                  bg="#00BCD4", fg="white", font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2"
                  ).pack(side="left", padx=4)
        tk.Button(tb, text="📊 Quick Health Check", command=self._quick_health,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=4)

        self._diag_text = scrolledtext.ScrolledText(
            frame, bg="#1E1E1E", fg="#81C784",
            font=("Consolas", 9), wrap="word",
            relief="flat", state="disabled"
        )
        self._diag_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._diag_text.tag_config("header", foreground="#00BCD4", font=("Consolas", 10, "bold"))
        self._diag_text.tag_config("ok", foreground="#4CAF50")
        self._diag_text.tag_config("fail", foreground="#F44336")
        self._diag_text.tag_config("warn", foreground="#FFC107")
        self._diag_text.tag_config("info", foreground="#ccc")

    def _append_diag(self, text: str, tag: str = "info"):
        self._diag_text.config(state="normal")
        self._diag_text.insert(tk.END, text + "\n", tag)
        self._diag_text.see(tk.END)
        self._diag_text.config(state="disabled")

    def _run_diagnostics(self):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from updater.health_checker import get_health_checker
                from jarvis_core.capability_registry import get_capability_registry

                self.after(0, lambda: self._append_diag("── Diagnostics ──", "header"))
                self.after(0, lambda: self._append_diag("Running health check...", "info"))

                hc = get_health_checker()
                result = hc.check()
                summary = HealthChecker.format_result(result)
                for line in summary.split("\n"):
                    tag = "ok" if "✅" in line else ("fail" if "❌" in line else "info")
                    self.after(0, lambda l=line, t=tag: self._append_diag(l, t))

                self.after(0, lambda: self._append_diag("\n── Capability Registry ──", "header"))
                reg = get_capability_registry()
                caps = reg.all()
                self.after(0, lambda: self._append_diag(f"Total capabilities: {len(caps)}", "info"))
                for cap in sorted(caps, key=lambda c: c.id):
                    status = cap.state.value
                    detail = cap.detail[:60] if cap.detail else ""
                    tag = "ok" if status == "AVAILABLE" else ("warn" if status in ("DEGRADED", "NOT_CONFIGURED") else "fail")
                    display = f"  {cap.id:30s} → {status}" + (f" ({detail})" if detail else "")
                    self.after(0, lambda d=display, t=tag: self._append_diag(d, t))

                self.after(0, lambda: self._append_diag("\n✅ Diagnostics complete.", "ok"))
            except Exception as e:
                self.after(0, lambda: self._append_diag(f"Error: {e}", "fail"))

        threading.Thread(target=worker, daemon=True).start()

    def _quick_health(self):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from updater.health_checker import get_health_checker
                hc = get_health_checker()
                result = hc.check()
                self.after(0, lambda: self._append_diag(
                    f"Health: {'✅ PASS' if result['healthy'] else '❌ FAIL'} "
                    f"({result['score']}/100) — {result.get('runtime_version','')}", "ok"
                    if result['healthy'] else "fail"))
            except Exception as e:
                self.after(0, lambda: self._append_diag(f"Health check error: {e}", "fail"))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Update Tab                                                          #
    # ------------------------------------------------------------------ #
    def _build_update_tab(self):
        frame = self._tab_frame("Updates")

        tb = tk.Frame(frame, bg="#252526")
        tb.pack(fill="x", padx=10, pady=(10, 5))
        tk.Button(tb, text="🔍 Check for Updates", command=self._check_update,
                  bg="#00BCD4", fg="white", font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2"
                  ).pack(side="left", padx=4)
        tk.Button(tb, text="💾 Create Backup", command=self._create_backup,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=4)
        tk.Button(tb, text="📋 List Backups", command=self._list_backups,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=4)

        self._update_text = scrolledtext.ScrolledText(
            frame, bg="#1E1E1E", fg="#ccc",
            font=("Consolas", 9), wrap="word",
            relief="flat", state="disabled"
        )
        self._update_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _append_update(self, text: str):
        self._update_text.config(state="normal")
        self._update_text.insert(tk.END, text + "\n")
        self._update_text.see(tk.END)
        self._update_text.config(state="disabled")

    def _check_update(self):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from updater import get_update_checker, get_version_manager
                vm = get_version_manager()
                checker = get_update_checker()
                self.after(0, lambda: self._append_update(f"Current version: {vm.get_version_string()}"))
                self.after(0, lambda: self._append_update("Checking GitHub releases..."))
                result = checker.check()
                if result["error"]:
                    self.after(0, lambda: self._append_update(f"Check error: {result['error']}"))
                    self.after(0, lambda: self._append_update("💡 Tip: Set GITHUB_OWNER/REPO env vars or configure in integrations."))
                elif result["update_available"]:
                    self.after(0, lambda: self._append_update(f"✅ Update available: v{result['latest_version']}"))
                    manifest = result.get("manifest", {})
                    if manifest.get("changelog"):
                        self.after(0, lambda: self._append_update(f"Changelog:\n{manifest['changelog'][:500]}"))
                else:
                    self.after(0, lambda: self._append_update("✅ You are on the latest version."))
            except Exception as e:
                self.after(0, lambda: self._append_update(f"Error: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _create_backup(self):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from updater import get_backup_manager
                bm = get_backup_manager()
                meta = bm.create_backup(label="manual_gui")
                self.after(0, lambda: self._append_update(
                    f"✅ Backup created: {meta['backup_id']} ({meta['file_count']} files, "
                    f"{meta['size_bytes'] // 1024}KB)"))
            except Exception as e:
                self.after(0, lambda: self._append_update(f"Backup error: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _list_backups(self):
        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from updater import get_backup_manager
                bm = get_backup_manager()
                backups = bm.list_backups()
                if not backups:
                    self.after(0, lambda: self._append_update("No backups found."))
                for b in backups:
                    self.after(0, lambda x=b: self._append_update(
                        f"  {x['backup_id']} — {x['created_at']} — "
                        f"{x['size_bytes'] // 1024}KB — {x.get('label','')}"))
            except Exception as e:
                self.after(0, lambda: self._append_update(f"Error: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Config Tab                                                          #
    # ------------------------------------------------------------------ #
    def _build_config_tab(self):
        frame = self._tab_frame("Configuration")

        content = tk.Frame(frame, bg="#252526")
        content.pack(fill="both", expand=True, padx=10, pady=10)

        config_items = [
            ("JARVIS_VERSION", "JarvisPro Version"),
            ("OPENAI_API_KEY", "OpenAI API Key"),
            ("TELEGRAM_BOT_TOKEN", "Telegram Bot Token"),
            ("DISCORD_BOT_TOKEN", "Discord Bot Token"),
            ("GITHUB_OWNER", "GitHub Owner"),
            ("GITHUB_REPO", "GitHub Repo"),
            ("WAITRESS_PORT", "API Port"),
            ("PERSONA", "AI Persona"),
        ]

        for env_key, label in config_items:
            row = tk.Frame(content, bg="#252526")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:", bg="#252526", fg="#888",
                     font=("Arial", 9), width=20, anchor="w"
                     ).pack(side="left")
            val = os.environ.get(env_key, os.environ.get(env_key.lower(), ""))
            if env_key in ("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN"):
                display = val[:8] + "***" if val else "(not set)"
            else:
                display = val or "(not set)"
            tk.Label(row, text=display, bg="#252526", fg="#4FC3F7",
                     font=("Consolas", 9)
                     ).pack(side="left")

    # ------------------------------------------------------------------ #
    #  About Tab                                                           #
    # ------------------------------------------------------------------ #
    def _build_about_tab(self):
        frame = self._tab_frame("About")
        info = [
            ("JARVIS AI PRO", "Advanced AI Desktop Assistant"),
            ("Version", "1.0.0"),
            ("Python", platform_python()),
            ("Platform", platform.system() + " " + platform.release()),
            ("Architecture", "Modular Brain + Event Bus + Capability Registry"),
            ("GUI Framework", "Tkinter"),
        ]
        for i, (k, v) in enumerate(info):
            row = tk.Frame(frame, bg="#252526" if i % 2 == 0 else "#1E1E1E")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{k}:", bg=row.cget("bg"), fg="#888",
                     font=("Arial", 9), width=22, anchor="w"
                     ).pack(side="left", padx=10, pady=4)
            tk.Label(row, text=v, bg=row.cget("bg"), fg="white",
                     font=("Arial", 9)
                     ).pack(side="left")


def platform_python():
    import platform
    return platform.python_version()
