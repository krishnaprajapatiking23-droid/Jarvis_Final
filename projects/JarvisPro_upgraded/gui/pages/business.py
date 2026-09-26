import tkinter as tk
import threading

from business.manager import business_manager
from gui.widgets.result_box import ResultBox


class BusinessPage(tk.Frame):

    def __init__(self, parent):

        super().__init__(parent, bg="#1E1E1E")

        title = tk.Label(
            self,
            text="Business Dashboard",
            bg="#1E1E1E",
            fg="white",
            font=("Arial", 22, "bold")
        )

        title.pack(pady=20)

        self.entry = tk.Entry(
            self,
            width=60,
            font=("Arial", 12)
        )

        self.entry.pack(pady=10)

        button = tk.Button(
            self,
            text="THIS IS THE REAL BUSINESS PAGE",
            command=self.research
        )

        button.pack(pady=10)

        self.output = ResultBox(self)

        self.output.pack(
            pady=10,
            padx=20,
            fill="both",
            expand=True
        )

    def research(self):

        command = self.entry.get().strip()

        if not command:
            return

        self.output.show("⏳ Researching... Please wait...")

        threading.Thread(
            target=self.run_research,
            args=(command,),
            daemon=True
        ).start()
    
    def run_research(self, command):

        answer = business_manager(command)

        self.after(
            0,
            lambda: self.output.show(answer)
        )