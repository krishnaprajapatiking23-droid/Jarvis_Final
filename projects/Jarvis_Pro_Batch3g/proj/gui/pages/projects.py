import tkinter as tk


class ProjectsPage(tk.Frame):

    def __init__(self, parent):

        super().__init__(parent, bg="#1E1E1E")

        title = tk.Label(
            self,
            text="Projects Page",
            bg="#1E1E1E",
            fg="white",
            font=("Arial", 22, "bold")
        )

        title.pack(pady=40)