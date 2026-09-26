import tkinter as tk


class Sidebar(tk.Frame):

    def __init__(self, parent, callback):

        super().__init__(parent, bg="#202020", width=220)

        self.pack_propagate(False)

        buttons = [

            ("🏠 Home", "home"),
            ("💬 Chat", "chat"),
            ("📂 Projects", "projects"),
            ("🧠 Memory", "memory"),
            ("💼 Business", "business"),
            ("💻 Coding", "coding"),
            ("⚙ Settings", "settings")

        ]

        for text, page in buttons:

            button = tk.Button(

                self,

                text=text,

                anchor="w",

                bg="#303030",

                fg="white",

                relief="flat",

                padx=15,

                command=lambda p=page: callback(p)

            )

            button.pack(fill="x", pady=3)