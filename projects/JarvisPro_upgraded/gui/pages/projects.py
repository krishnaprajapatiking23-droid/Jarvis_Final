"""
Projects Page — Project/task management backed by projects/manager.py.
"""
import tkinter as tk
from tkinter import ttk
import os

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ProjectsPage(tk.Frame):
    """Project management backed by projects/manager.py."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------ #
    #  UI Layout                                                          #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        title = tk.Label(
            self, text="Projects & Tasks", bg="#1E1E1E", fg="#00BCD4",
            font=("Arial", 16, "bold")
        )
        title.pack(anchor="w", padx=20, pady=(15, 5))

        # Toolbar
        tb = tk.Frame(self, bg="#1E1E1E")
        tb.pack(fill="x", padx=15, pady=(0, 5))
        for label_text, cmd in [
            ("➕ New Project", self._new_project),
            ("📋 New Task", self._new_task),
            ("✅ Complete Task", self._complete_task),
            ("🔄 Refresh", self._refresh),
        ]:
            tk.Button(tb, text=label_text, command=cmd,
                      bg="#37474F", fg="white", relief="flat",
                      cursor="hand2", font=("Arial", 9)
                      ).pack(side="left", padx=3)

        # Command entry
        cmd_frame = tk.Frame(self, bg="#1E1E1E")
        cmd_frame.pack(fill="x", padx=15, pady=(0, 5))
        tk.Label(cmd_frame, text="Command:", bg="#1E1E1E", fg="#888",
                 font=("Arial", 9)
                 ).pack(side="left", padx=(0, 5))
        self._cmd_entry = tk.Entry(
            cmd_frame, bg="#252526", fg="white",
            font=("Consolas", 10), insertbackground="white", relief="flat"
        )
        self._cmd_entry.pack(side="left", fill="x", expand=True)
        self._cmd_entry.bind("<Return>", lambda e: self._run_command())
        tk.Button(cmd_frame, text="Run", command=self._run_command,
                  bg="#00BCD4", fg="white", relief="flat",
                  cursor="hand2"
                  ).pack(side="left", padx=(5, 0))

        # Projects list (treeview)
        list_frame = tk.Frame(self, bg="#1E1E1E")
        list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        columns = ("project", "task", "status", "priority", "due")
        self._tree = ttk.Treeview(
            list_frame, columns=columns, show="headings",
            style="Dark.Treeview"
        )
        col_widths = {"project": 150, "task": 250, "status": 100, "priority": 80, "due": 120}
        for col in columns:
            self._tree.heading(col, text=col.title())
            self._tree.column(col, width=col_widths.get(col, 100))
        self._tree.pack(side="left", fill="both", expand=True)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        self._tree.config(yscrollcommand=scroll.set)
        scroll.config(command=self._tree.yview)

    # ------------------------------------------------------------------ #
    #  Refresh                                                             #
    # ------------------------------------------------------------------ #
    def _refresh(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from projects.manager import project_manager
            result = project_manager("show project")
            lines = (result or "").strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("─") or line.startswith("="):
                    continue
                # Try to parse: Project | Task | Status
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    project = parts[0][:20]
                    task = parts[1][:40] if len(parts) > 1 else ""
                    status = parts[2] if len(parts) > 2 else "active"
                    self._tree.insert("", "end", values=(project, task, status, "medium", "—"))
        except Exception as e:
            self._tree.insert("", "end", values=("Error", str(e)[:40], "—", "—", "—"))

    # ------------------------------------------------------------------ #
    #  Actions                                                             #
    # ------------------------------------------------------------------ #
    def _run_command(self):
        cmd = self._cmd_entry.get().strip()
        if not cmd:
            return
        self._cmd_entry.delete(0, tk.END)
        try:
            import sys; sys.path.insert(0, JARVIS_ROOT)
            from projects.manager import project_manager
            result = project_manager(cmd)
            self._refresh()
        except Exception as e:
            self._tree.insert("", "end", values=("Error", str(e)[:40], "—", "—", "—"))

    def _new_project(self):
        name = tk.simpledialog.askstring("New Project", "Project name:", parent=self)
        if name:
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from projects.manager import project_manager
                project_manager(f"create project {name}")
                self._refresh()
            except Exception as e:
                pass

    def _new_task(self):
        task = tk.simpledialog.askstring("New Task", "Task description:", parent=self)
        if task:
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from projects.manager import project_manager
                project_manager(f"add task {task}")
                self._refresh()
            except Exception:
                pass

    def _complete_task(self):
        sel = self._tree.selection()
        if sel:
            item = self._tree.item(sel[0])
            values = item.get("values", [])
            if values and len(values) > 1:
                task = values[1]
                try:
                    import sys; sys.path.insert(0, JARVIS_ROOT)
                    from projects.manager import project_manager
                    project_manager(f"complete task {task}")
                    self._refresh()
                except Exception:
                    pass
