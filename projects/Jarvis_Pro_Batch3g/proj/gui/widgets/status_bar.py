import tkinter as tk


class StatusBar(tk.Label):

    def __init__(self, parent):

        super().__init__(
            parent,
            text="🟢 Ready",
            anchor="w",
            bg="#2D2D30",
            fg="white",
            padx=10
        )

    def set(self, message):

        self.config(text=message)