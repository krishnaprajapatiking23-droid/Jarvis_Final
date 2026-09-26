import tkinter as tk


class TaskPanel(tk.Frame):

    def __init__(self, parent):

        super().__init__(parent, bg="#2D2D30")

        title = tk.Label(
            self,
            text="Tasks",
            bg="#2D2D30",
            fg="white",
            font=("Arial", 12, "bold")
        )

        title.pack(anchor="w", padx=10, pady=5)

        self.listbox = tk.Listbox(
            self,
            bg="#252526",
            fg="white",
            height=12,
            borderwidth=0
        )

        self.listbox.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

    def update_tasks(self, tasks):

        self.listbox.delete(0, tk.END)

        for task in tasks:

            self.listbox.insert(
                tk.END,
                f"{task['status']}  {task['task']}"
            )