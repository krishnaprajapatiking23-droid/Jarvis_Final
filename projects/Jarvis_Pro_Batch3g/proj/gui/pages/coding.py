import tkinter as tk


class CodingPage(tk.Frame):

    def __init__(self, parent):

        super().__init__(parent, bg="#1E1E1E")

        title = tk.Label(
            self,
            text="Coding Dashboard",
            bg="#1E1E1E",
            fg="white",
            font=("Arial", 22, "bold")
        )

        title.pack(pady=40)