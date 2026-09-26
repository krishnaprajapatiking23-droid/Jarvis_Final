import tkinter as tk


class ResultBox(tk.Text):

    def __init__(self, parent):

        super().__init__(

            parent,

            height=20,

            width=90,

            bg="#252526",

            fg="white",

            font=("Consolas", 11),

            wrap="word"

        )

    def show(self, text):

        self.delete("1.0", tk.END)

        self.insert(tk.END, text)