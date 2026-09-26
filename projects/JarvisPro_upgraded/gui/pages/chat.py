"""
Chat Page — Full-featured Jarvis chat backed by route_command.
Replaces the old main_window inline chat with a proper page widget.
"""
import tkinter as tk
from tkinter import scrolledtext
import threading
import os

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ChatPage(tk.Frame):
    """Standalone chat page using the real Jarvis brain pipeline."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._build_ui()

    def _build_ui(self):
        # Title bar
        title_bar = tk.Frame(self, bg="#252526")
        title_bar.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(
            title_bar, text="JARVIS CHAT", bg="#252526", fg="#00BCD4",
            font=("Arial", 13, "bold")
        ).pack(side="left", padx=8, pady=6)

        self._status_lbl = tk.Label(
            title_bar, text="● READY", bg="#252526", fg="#4CAF50",
            font=("Arial", 9, "bold")
        )
        self._status_lbl.pack(side="right", padx=8, pady=6)

        # Chat history
        chat_frame = tk.Frame(self, bg="#1E1E1E")
        chat_frame.pack(fill="both", expand=True, padx=10, pady=(5, 0))

        self._chat = scrolledtext.ScrolledText(
            chat_frame, bg="#1E1E1E", fg="white",
            font=("Consolas", 11), wrap="word",
            insertbackground="white", relief="flat", state="disabled"
        )
        self._chat.pack(fill="both", expand=True)

        self._chat.tag_config("user", foreground="#4FC3F7", font=("Arial", 11, "bold"))
        self._chat.tag_config("jarvis", foreground="#81C784", font=("Arial", 11))
        self._chat.tag_config("system", foreground="#FFC107", font=("Arial", 9, "italic"))
        self._chat.tag_config("error", foreground="#F44336", font=("Arial", 10))

        # Input area
        input_frame = tk.Frame(self, bg="#252526")
        input_frame.pack(fill="x", padx=10, pady=(5, 10))

        self._entry = tk.Entry(
            input_frame, bg="#1E1E1E", fg="white",
            font=("Arial", 13), insertbackground="white",
            relief="flat"
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=8)
        self._entry.bind("<Return>", lambda e: self._send())

        self._send_btn = tk.Button(
            input_frame, text="Send", command=self._send,
            bg="#00BCD4", fg="white", font=("Arial", 11, "bold"),
            width=8, relief="flat", cursor="hand2"
        )
        self._send_btn.pack(side="left", pady=8)

        self._voice_btn = tk.Button(
            input_frame, text="🎤 Voice", command=self._voice,
            bg="#37474F", fg="white", font=("Arial", 11),
            width=8, relief="flat", cursor="hand2"
        )
        self._voice_btn.pack(side="left", padx=(5, 0), pady=8)

        self._append("jarvis", "JARVIS AI — Ready to assist.\nAsk me anything.\n")

    # ------------------------------------------------------------------ #
    #  Send / Receive                                                     #
    # ------------------------------------------------------------------ #
    def _send(self, event=None):
        message = self._entry.get().strip()
        if not message:
            return
        self._entry.delete(0, tk.END)
        self._set_busy(True)
        self._append("user", f"You: {message}\n")
        threading.Thread(target=self._request_worker, args=(message,), daemon=True).start()

    def _request_worker(self, message: str):
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from core.router import route_command
            from conversation.identity import identity
            answer = route_command(message, identity.owner())
        except Exception as e:
            answer = f"Error: {type(e).__name__}: {e}"
        self.after(0, self._display_answer, answer)

    def _display_answer(self, answer: str):
        self._append("jarvis", f"Jarvis: {answer}\n")
        self._set_busy(False)

    # ------------------------------------------------------------------ #
    #  Voice                                                              #
    # ------------------------------------------------------------------ #
    def _voice(self):
        self._set_busy(True)
        self._append("system", "🎤 Listening...\n")
        threading.Thread(target=self._voice_worker, daemon=True).start()

    def _voice_worker(self):
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from voice.manager import listen
            from conversation.identity import identity
            text, answer = listen(identity.owner())
        except Exception as e:
            text, answer = "", f"Voice unavailable: {e}"
        self.after(0, self._voice_done, text, answer)

    def _voice_done(self, text: str, answer: str):
        if text:
            self._append("user", f"You: {text}\n")
        self._append("jarvis", f"Jarvis: {answer}\n")
        self._set_busy(False)

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _append(self, tag: str, text: str):
        self._chat.config(state="normal")
        self._chat.insert(tk.END, text + "\n", tag)
        self._chat.see(tk.END)
        self._chat.config(state="disabled")

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self._entry.config(state=state)
        self._send_btn.config(state=state)
        self._voice_btn.config(state=state)
        self._status_lbl.config(
            text="● PROCESSING..." if busy else "● READY",
            fg="#FFC107" if busy else "#4CAF50"
        )
