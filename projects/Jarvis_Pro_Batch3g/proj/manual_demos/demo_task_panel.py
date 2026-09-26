import tkinter as tk

from gui.widgets.task_panel import TaskPanel

root = tk.Tk()

panel = TaskPanel(root)

panel.pack(fill="both", expand=True)

panel.update_tasks([
    {"task": "Understand Request", "status": "✔"},
    {"task": "Choose Brain", "status": "✔"},
    {"task": "Ask AI", "status": "⏳"},
    {"task": "Generate Response", "status": "⬜"}
])

root.mainloop()