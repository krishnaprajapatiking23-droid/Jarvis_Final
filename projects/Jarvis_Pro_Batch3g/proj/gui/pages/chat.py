import tkinter as tk


class ChatPage(tk.Frame):

    def __init__(self, parent):

        super().__init__(parent)

        tk.Label(

            self,

            text="Chat Page",

            font=("Arial", 22)

        ).pack(pady=50)