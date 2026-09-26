"""
Memory Page — Real memory, notes, reminders management.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import os

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MemoryPage(tk.Frame):
    """Memory/Notes/Reminders management backed by real kernel subsystems."""

    def __init__(self, parent):
        super().__init__(parent, bg="#1E1E1E")
        self._kernel = None
        self._tabs = None
        self._memory_listbox = None
        self._notes_listbox = None
        self._reminders_listbox = None
        self._build_ui()

    def _get_kernel(self):
        if self._kernel is None:
            try:
                import sys; sys.path.insert(0, JARVIS_ROOT)
                from jarvis_core.kernel import get_kernel
                self._kernel = get_kernel()
            except Exception as e:
                print(f"[MemoryPage] Kernel unavailable: {e}")
        return self._kernel

    # ------------------------------------------------------------------ #
    #  UI Layout                                                          #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        title = tk.Label(
            self, text="Memory & Knowledge", bg="#1E1E1E", fg="#00BCD4",
            font=("Arial", 16, "bold")
        )
        title.pack(anchor="w", padx=20, pady=(15, 5))

        self._tabs = ttk.Notebook(self)
        self._tabs.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Memory tab
        self._build_memory_tab()
        # Notes tab
        self._build_notes_tab()
        # Reminders tab
        self._build_reminders_tab()

        self._refresh_all()

    def _build_memory_tab(self):
        frame = tk.Frame(self._tabs, bg="#252526")
        self._tabs.add(frame, text="  Memory  ")

        # Toolbar
        tb = tk.Frame(frame, bg="#252526")
        tb.pack(fill="x", padx=10, pady=(10, 5))
        tk.Button(tb, text="🔄 Refresh", command=self._refresh_memory,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="➕ Add Entry", command=self._add_memory_entry,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="🗑️ Delete", command=self._delete_memory_entry,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)

        # List + detail
        list_frame = tk.Frame(frame, bg="#252526")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._memory_listbox = tk.Listbox(
            list_frame, bg="#1E1E1E", fg="white",
            font=("Consolas", 10), selectbackground="#00BCD4",
            selectforeground="black", relief="flat"
        )
        self._memory_listbox.pack(side="left", fill="both", expand=True)
        self._memory_listbox.bind("<<ListboxSelect>>", self._on_memory_select)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        self._memory_listbox.config(yscrollcommand=scroll.set)
        scroll.config(command=self._memory_listbox.yview)

        self._memory_detail = tk.Text(
            frame, bg="#1E1E1E", fg="#ccc",
            font=("Consolas", 9), wrap="word",
            height=6, relief="flat", state="disabled"
        )
        self._memory_detail.pack(fill="x", padx=10, pady=(0, 10))

    def _build_notes_tab(self):
        frame = tk.Frame(self._tabs, bg="#252526")
        self._tabs.add(frame, text="  Notes  ")

        tb = tk.Frame(frame, bg="#252526")
        tb.pack(fill="x", padx=10, pady=(10, 5))
        tk.Button(tb, text="🔄 Refresh", command=self._refresh_notes,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="➕ New Note", command=self._add_note,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="🗑️ Delete", command=self._delete_note,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)

        list_frame = tk.Frame(frame, bg="#252526")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._notes_listbox = tk.Listbox(
            list_frame, bg="#1E1E1E", fg="white",
            font=("Consolas", 10), selectbackground="#00BCD4",
            selectforeground="black", relief="flat"
        )
        self._notes_listbox.pack(side="left", fill="both", expand=True)
        self._notes_listbox.bind("<<ListboxSelect>>", self._on_note_select)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        self._notes_listbox.config(yscrollcommand=scroll.set)
        scroll.config(command=self._notes_listbox.yview)

        self._note_text = tk.Text(
            frame, bg="#1E1E1E", fg="white",
            font=("Consolas", 10), wrap="word",
            relief="flat"
        )
        self._note_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_reminders_tab(self):
        frame = tk.Frame(self._tabs, bg="#252526")
        self._tabs.add(frame, text="  Reminders  ")

        tb = tk.Frame(frame, bg="#252526")
        tb.pack(fill="x", padx=10, pady=(10, 5))
        tk.Button(tb, text="🔄 Refresh", command=self._refresh_reminders,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="✅ Complete", command=self._complete_reminder,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(tb, text="🗑️ Delete", command=self._delete_reminder,
                  bg="#37474F", fg="white", relief="flat", cursor="hand2"
                  ).pack(side="left", padx=2)

        columns = ("rid", "rtxt", "rtime", "rrep", "ract")
        self._reminders_tree = ttk.Treeview(
            frame, columns=columns, show="headings",
            height=12
        )
        headers = {"rid": "ID", "rtxt": "Text", "rtime": "Time", "rrep": "Repeat", "ract": "Active"}
        for col in columns:
            self._reminders_tree.heading(col, text=headers.get(col, col.title()))
            self._reminders_tree.column(col, width=50 if col == "rid" else 160)
        self._reminders_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ------------------------------------------------------------------ #
    #  Refresh                                                            #
    # ------------------------------------------------------------------ #
    def _refresh_all(self):
        self._refresh_memory()
        self._refresh_notes()
        self._refresh_reminders()

    def _refresh_memory(self):
        self._memory_listbox.delete(0, tk.END)
        kernel = self._get_kernel()
        if kernel is None:
            self._memory_listbox.insert(0, "  [ Kernel unavailable — check logs ]")
            return
        try:
            # Collect memory entries from kernel memory subsystem
            entries = []
            mem = getattr(kernel, "memory", None)
            if mem:
                # Try various common memory interface methods
                for method in ("all", "entries", "get_all", "list_entries"):
                    if hasattr(mem, method):
                        entries = getattr(mem, method)()
                        if callable(entries):
                            entries = entries()
                        break
                # Fallback: try listing the attribute
                if not entries:
                    for attr_name in dir(mem):
                        if not attr_name.startswith("_"):
                            attr = getattr(mem, attr_name, None)
                            if isinstance(attr, (list, tuple, dict)):
                                if isinstance(attr, dict):
                                    for k, v in list(attr.items())[:50]:
                                        entries.append(f"{k}: {v}")
                                else:
                                    for v in list(attr)[:50]:
                                        entries.append(str(v))
                                break
            for entry in (entries or [])[:100]:
                self._memory_listbox.insert(tk.END, f"  {entry}")
        except Exception as e:
            self._memory_listbox.insert(0, f"  [ Error: {e} ]")

    def _refresh_notes(self):
        self._notes_listbox.delete(0, tk.END)
        kernel = self._get_kernel()
        if kernel is None:
            self._notes_listbox.insert(0, "  [ Kernel unavailable ]")
            return
        try:
            notes = getattr(kernel, "notes", None)
            if notes:
                for method in ("all", "list", "entries", "get_all"):
                    if hasattr(notes, method):
                        items = getattr(notes, method)()
                        if callable(items):
                            items = items()
                        for item in (items or [])[:100]:
                            title = str(item)[:60]
                            self._notes_listbox.insert(tk.END, f"  {title}")
                        break
            else:
                self._notes_listbox.insert(0, "  [ No notes manager ]")
        except Exception as e:
            self._notes_listbox.insert(0, f"  [ Error: {e} ]")

    def _refresh_reminders(self):
        for item in self._reminders_tree.get_children():
            self._reminders_tree.delete(item)
        kernel = self._get_kernel()
        if kernel is None:
            self._reminders_tree.insert("", "end", values=("—", "Kernel unavailable", "—", "—", "—"))
            return
        try:
            reminders = getattr(kernel, "reminders", None)
            if reminders:
                for method in ("all", "list", "upcoming", "get_all"):
                    if hasattr(reminders, method):
                        items = getattr(reminders, method)()
                        if callable(items):
                            items = items()
                        for item in (items or [])[:50]:
                            row = self._parse_reminder(item)
                            self._reminders_tree.insert("", "end", values=row)
                        break
            else:
                self._reminders_tree.insert("", "end", values=("—", "No reminders manager", "—", "—", "—"))
        except Exception as e:
            self._reminders_tree.insert("", "end", values=("—", f"Error: {e}", "—", "—", "—"))

    def _parse_reminder(self, item) -> tuple:
        """Convert a reminder object into a table row."""
        if isinstance(item, dict):
            return (
                item.get("id", "—")[:8],
                item.get("text", "—")[:40],
                item.get("time", item.get("datetime", item.get("scheduled_at", "—")))[:20],
                item.get("repeat", "—")[:15],
                "✓" if item.get("active", True) else "✗",
            )
        return ("—", str(item)[:40], "—", "—", "—")

    # ------------------------------------------------------------------ #
    #  Actions                                                            #
    # ------------------------------------------------------------------ #
    def _on_memory_select(self, event):
        pass

    def _on_note_select(self, event):
        pass

    def _add_memory_entry(self):
        self._show_add_dialog("Add Memory Entry", self._do_add_memory)

    def _do_add_memory(self, text: str):
        kernel = self._get_kernel()
        if kernel:
            try:
                mem = getattr(kernel, "memory", None)
                if mem:
                    for method in ("add", "set", "store", "remember", "create"):
                        if hasattr(mem, method):
                            getattr(mem, method)(text)
                            break
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add memory: {e}")
        self._refresh_memory()

    def _delete_memory_entry(self):
        sel = self._memory_listbox.curselection()
        if not sel:
            return
        self._memory_listbox.delete(sel[0])

    def _add_note(self):
        title = tk.simpledialog.askstring("New Note", "Note title:", parent=self)
        if title:
            kernel = self._get_kernel()
            if kernel:
                try:
                    notes = getattr(kernel, "notes", None)
                    if notes:
                        for method in ("add", "create", "new", "append"):
                            if hasattr(notes, method):
                                getattr(notes, method)(title, "")
                                break
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create note: {e}")
            self._refresh_notes()

    def _delete_note(self):
        sel = self._notes_listbox.curselection()
        if sel:
            self._notes_listbox.delete(sel[0])

    def _complete_reminder(self):
        sel = self._reminders_tree.selection()
        if sel:
            self._reminders_tree.delete(sel[0])

    def _delete_reminder(self):
        sel = self._reminders_tree.selection()
        if sel:
            self._reminders_tree.delete(sel[0])

    def _show_add_dialog(self, title: str, callback):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg="#252526")
        dialog.geometry("400x120")
        dialog.transient(self)
        tk.Label(dialog, text=title, bg="#252526", fg="white",
                 font=("Arial", 11)).pack(pady=(10, 5))
        entry = tk.Entry(dialog, bg="#1E1E1E", fg="white", font=("Arial", 11))
        entry.pack(fill="x", padx=20)
        entry.focus()

        def on_ok():
            callback(entry.get().strip())
            dialog.destroy()

        tk.Button(dialog, text="Add", command=on_ok,
                  bg="#00BCD4", fg="white", relief="flat").pack(pady=10)
        entry.bind("<Return>", lambda e: on_ok())
