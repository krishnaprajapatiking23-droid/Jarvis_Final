from conversation.identity import identity
from voice.manager import listen
import threading
try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:
    tk = None
    scrolledtext = None



class JarvisGUI:

    def __init__(self):

        if tk is None:
            raise RuntimeError("GUI unavailable: tkinter is not installed")
        from gui.pages.home import HomePage
        from gui.pages.chat import ChatPage
        from gui.pages.business import BusinessPage
        from gui.pages.coding import CodingPage
        from gui.pages.memory import MemoryPage
        from gui.pages.projects import ProjectsPage
        from gui.pages.settings import SettingsPage
        from gui.sidebar import Sidebar

        self.root = tk.Tk()

        self.root.title("JARVIS PRO")
        self.root.geometry("1400x800")
        self.root.configure(bg="#1E1E1E")
        
        # ==========================
        # Sidebar
        # ==========================

        self.sidebar = Sidebar(self.root, self.show_page)
        self.sidebar.pack(side="left", fill="y")

        # ==========================
        # Main Content Area
        # ==========================

        self.content = tk.Frame(
            self.root,
            bg="#1E1E1E"
        )

        self.content.pack(
            side="right",
            fill="both",
            expand=True
        )
        # ==========================
        # Pages
        # ==========================

        self.pages = {
        
            "home": HomePage(self.content),

            "chat": ChatPage(self.content),

            "business": BusinessPage(self.content),

            "coding": CodingPage(self.content),

            "memory": MemoryPage(self.content),

            "projects": ProjectsPage(self.content),

            "settings": SettingsPage(self.content)

        }

        # ==========================
        # Chat Window
        # ==========================

        self.chat = scrolledtext.ScrolledText(
            self.root,
            bg="#252526",
            fg="white",
            font=("Consolas", 11)
        )

        self.chat.pack(
            side="right",
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        self.chat.tag_config(
            "user",
            foreground="#4FC3F7",
            font=("Arial", 11, "bold")
        )

        self.chat.tag_config(
            "jarvis",
            foreground="#81C784",
            font=("Arial", 11, "bold")
        )

        # ==========================
        # Input Box
        # ==========================

        self.entry = tk.Entry(
            self.root,
            font=("Arial", 13)
        )

        self.entry.pack(fill="x", padx=10)

        self.entry.bind("<Return>", self.send)

        # ==========================
        # Send Button
        # ==========================

        # ==========================
        # Bottom Buttons
        # ==========================

        self.bottom_frame = tk.Frame(
            self.root,
            bg="#1E1E1E"
        )

        self.bottom_frame.pack(fill="x", pady=10)

        self.button = tk.Button(
            self.bottom_frame,
            text="Send",
            command=self.send,
            width=12
        )

        self.button.pack(
            side="left",
            padx=10
        )

        self.voice_button = tk.Button(
            self.bottom_frame,
            text="🎤 Voice",
            command=lambda: threading.Thread(
                target=self.voice_chat,
                daemon=True
            ).start(),
            width=12
        )

        self.voice_button.pack(
            side="left"
        )

        # Show the Home page when Jarvis starts
        self.show_page("home")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _display_answer(self, answer):
        self.chat.insert(tk.END, "🤖 Jarvis\n", "jarvis")
        self.chat.insert(tk.END, str(answer) + "\n\n")
        self.chat.see(tk.END)
        self.button.configure(state="normal")

    def _request_worker(self, message):
        try:
            from core.router import route_command
            answer = route_command(message, identity.owner())
        except Exception as error: answer = f"Request failed: {type(error).__name__}: {error}"
        self.root.after(0, self._display_answer, answer)

    def send(self, event=None):
        message = self.entry.get().strip()
        if not message: return
        self.chat.insert(tk.END, "\n🧑 You\n", "user")
        self.chat.insert(tk.END, message + "\n\n")
        self.entry.delete(0, tk.END); self.button.configure(state="disabled")
        threading.Thread(target=self._request_worker, args=(message,), daemon=True, name="jarvis-gui-request").start()

    def show_page(self, page):

        # Hide all pages
        for frame in self.pages.values():
            frame.pack_forget()

        # Show selected page
        self.pages[page].pack(
            fill="both",
            expand=True
        )

    def voice_chat(self):
        self.root.after(0, self.chat.insert, tk.END, "\n🎤 Listening...\n")
        try: text, answer = listen(identity.owner())
        except Exception as error: text, answer = "", f"Voice unavailable: {error}"
        def update():
            self.chat.insert(tk.END, "🧑 You\n", "user"); self.chat.insert(tk.END, str(text) + "\n\n"); self._display_answer(answer)
        self.root.after(0, update)

    def close(self):
        try:
            from voice.continuous_listener import stop
            stop()
            from voice.tts import tts
            tts.stop()
        finally:
            self.root.destroy()

    def run(self):

        self.show_page("home")

        self.root.mainloop()