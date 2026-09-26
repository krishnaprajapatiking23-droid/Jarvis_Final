"""
Coding Page — AI coding assistant backed by the Jarvis brain.
"""
import tkinter as tk
from tkinter import scrolledtext
import threading
import os

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CodingPage(tk.Frame):
    """AI coding assistant powered by the Jarvis brain pipeline."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI Layout                                                          #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#252526")
        header.pack(fill="x", padx=15, pady=(15, 5))
        tk.Label(
            header, text="AI Coding Assistant", bg="#252526", fg="#00BCD4",
            font=("Arial", 14, "bold")
        ).pack(side="left")
        tk.Label(
            header, text="Powered by Jarvis Brain", bg="#252526", fg="#555",
            font=("Arial", 9)
        ).pack(side="left", padx=(8, 0))

        # Quick actions row
        quick_frame = tk.Frame(self, bg="#1E1E1E")
        quick_frame.pack(fill="x", padx=15, pady=(0, 5))

        shortcuts = [
            ("Explain Code", "explain this code: "),
            ("Debug Error", "debug this error: "),
            ("Write Test", "write unit tests for: "),
            ("Refactor", "refactor this code: "),
            ("Add Comments", "add comments to: "),
            ("Review Code", "review this code: "),
        ]
        for label_text, prefix in shortcuts:
            tk.Button(
                quick_frame, text=label_text, command=lambda p=prefix: self._insert_prefix(p),
                bg="#37474F", fg="white", font=("Arial", 8),
                relief="flat", cursor="hand2", width=12
            ).pack(side="left", padx=2, pady=2)

        # Code input
        input_label = tk.Label(
            self, text="Code / Question:", bg="#1E1E1E", fg="#888",
            font=("Arial", 10), anchor="w"
        )
        input_label.pack(anchor="w", padx=15)

        self._input = scrolledtext.ScrolledText(
            self, bg="#1E1E1E", fg="#D4D4D4",
            font=("Consolas", 10), wrap="word",
            insertbackground="#D4D4D4", relief="flat",
            height=12
        )
        self._input.pack(fill="x", padx=15, pady=(0, 5))
        self._input.tag_config("prompt", foreground="#00BCD4")

        # Action buttons
        btn_frame = tk.Frame(self, bg="#1E1E1E")
        btn_frame.pack(fill="x", padx=15, pady=(0, 5))
        tk.Button(
            btn_frame, text="🤖 Ask Jarvis", command=self._ask,
            bg="#00BCD4", fg="white", font=("Arial", 11, "bold"),
            relief="flat", cursor="hand2", width=15
        ).pack(side="left", padx=3)
        tk.Button(
            btn_frame, text="🧹 Clear", command=lambda: (
                self._input.delete("1.0", tk.END),
                self._output.config(state="normal"),
                self._output.delete("1.0", tk.END),
                self._output.config(state="disabled")
            ),
            bg="#37474F", fg="white", relief="flat",
            cursor="hand2", width=12
        ).pack(side="left", padx=3)

        self._status_lbl = tk.Label(
            btn_frame, text="● Ready", bg="#1E1E1E", fg="#4CAF50",
            font=("Arial", 9)
        )
        self._status_lbl.pack(side="right", padx=10)

        # Output
        output_label = tk.Label(
            self, text="Jarvis Response:", bg="#1E1E1E", fg="#888",
            font=("Arial", 10), anchor="w"
        )
        output_label.pack(anchor="w", padx=15)

        self._output = scrolledtext.ScrolledText(
            self, bg="#0D1117", fg="#81C784",
            font=("Consolas", 10), wrap="word",
            relief="flat", height=16, state="disabled"
        )
        self._output.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self._output.tag_config("user_q", foreground="#4FC3F7", font=("Consolas", 10, "bold"))
        self._output.tag_config("error", foreground="#F44336")

        self._insert_placeholder()

    def _insert_placeholder(self):
        self._input.insert("1.0", '# Paste your code or question here\n# Examples:\n# - "Write a Python function to sort a list"\n# - "Explain the decorator pattern"\n# - "Debug: IndexError at line 42"\n')

    def _insert_prefix(self, prefix: str):
        self._input.insert(tk.END, f"\n{prefix}")
        self._input.focus()

    # ------------------------------------------------------------------ #
    #  Ask Jarvis                                                          #
    # ------------------------------------------------------------------ #
    def _ask(self):
        code = self._input.get("1.0", tk.END).strip()
        if not code or code.startswith("# Paste"):
            return
        self._output.config(state="normal")
        self._output.insert(tk.END, f"\n🧑 You:\n{code[:200]}...\n\n", "user_q")
        self._output.config(state="disabled")
        self._set_busy(True)

        def worker():
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from core.router import route_command
                from conversation.identity import identity
                answer = route_command(code, identity.owner())
            except Exception as e:
                answer = f"Error: {type(e).__name__}: {e}"
            self.after(0, self._show_response, answer)

        threading.Thread(target=worker, daemon=True).start()

    def _show_response(self, answer: str):
        tag = "" if not answer.startswith("Error") else "error"
        self._output.config(state="normal")
        self._output.insert(tk.END, f"🤖 Jarvis:\n{answer}\n\n", tag)
        self._output.see(tk.END)
        self._output.config(state="disabled")
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._status_lbl.config(
            text="● Processing..." if busy else "● Ready",
            fg="#FFC107" if busy else "#4CAF50"
        )
