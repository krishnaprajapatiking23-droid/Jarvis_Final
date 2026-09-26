"""Computer automation manager (Section 12).

Wraps the existing `automation/` helpers behind one kernel-registered manager
so window moves, archives, computer search and process control all go through
policy checks, tracing and analytics instead of being called ad hoc.

Every operation returns a dict with an explicit outcome:
  ok | invalid_input | permission_denied | unavailable | failure | not_found
Nothing returns a bare True, and nothing pretends to have acted when the
underlying OS backend is missing (headless Linux has no window manager).
"""
from __future__ import annotations

import fnmatch
import os
import shutil
import signal
import zipfile
from typing import Any, Dict, List, Optional, Sequence

# Processes that must never be terminated by automation, even if the user asks
# by name. Killing these takes the machine (or Jarvis itself) down.
CRITICAL_PROCESSES = frozenset({
    "systemd", "init", "kernel_task", "launchd", "kthreadd", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "smss.exe",
    "svchost.exe", "explorer.exe", "python", "python3", "jarvis", "jarvis.py",
    "sshd", "dbus-daemon", "logind",
})

MAX_SEARCH_RESULTS = 500
_ARCHIVE_MEMBER_LIMIT = 20000


class AutomationError(RuntimeError):
    pass


def _outcome(status: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": status == "ok", "status": status}
    out.update(extra)
    return out


def _safe_path(path: str, roots: Optional[Sequence[str]]) -> str:
    """Resolve a path and refuse traversal outside the allowed roots."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    resolved = os.path.realpath(os.path.expanduser(path))
    if roots:
        allowed = [os.path.realpath(os.path.expanduser(r)) for r in roots]
        if not any(resolved == a or resolved.startswith(a + os.sep) for a in allowed):
            raise PermissionError(f"{resolved} is outside the allowed roots {allowed}")
    return resolved


class AutomationManager:
    """Capability: "automation". Registered on the kernel manager registry.

    state: none of its own; every action is traced through observability and
    scored in analytics, and destructive actions are gated by the policy engine.
    """

    capability = "automation"

    def __init__(self, kernel: Any = None, allowed_roots: Optional[Sequence[str]] = None):
        self.kernel = kernel
        self.allowed_roots = list(allowed_roots) if allowed_roots else None

    # ---------------- infrastructure ----------------
    def _guard(self, scope: str, action: str) -> Dict[str, Any]:
        kernel = self.kernel
        if kernel is None or not hasattr(kernel, "guard"):
            return {"allowed": True, "reason": "no policy engine attached"}
        try:
            return kernel.guard(scope, action)
        except Exception as exc:  # policy must never hard-crash automation
            return {"allowed": False, "reason": f"policy error: {type(exc).__name__}: {exc}"}

    def _record(self, action: str, ok: bool, detail: str = "") -> None:
        kernel = self.kernel
        analytics = getattr(kernel, "analytics", None)
        if analytics is None:
            return
        try:
            analytics.record("tool", f"automation.{action}", ok, error=detail or None)
        except Exception:
            pass

    def health(self) -> Dict[str, Any]:
        return {
            "available": True,
            "window_backend": self._window_backend()[0],
            "process_backend": self._process_backend(),
            "allowed_roots": self.allowed_roots or "unrestricted",
        }

    # ---------------- windows ----------------
    def _window_backend(self):
        try:
            import pygetwindow  # type: ignore
            return "pygetwindow", pygetwindow
        except Exception:
            pass
        if shutil.which("wmctrl"):
            return "wmctrl", None
        return None, None

    def list_windows(self) -> Dict[str, Any]:
        name, mod = self._window_backend()
        if name is None:
            return _outcome("unavailable", reason="no window manager backend (pygetwindow/wmctrl)")
        if name == "pygetwindow":
            titles = [t for t in mod.getAllTitles() if t]
            return _outcome("ok", backend=name, windows=titles)
        import subprocess
        proc = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return _outcome("failure", backend=name, error=proc.stderr.strip())
        titles = [line.split(None, 3)[-1] for line in proc.stdout.splitlines() if line.strip()]
        return _outcome("ok", backend=name, windows=titles)

    def move_window(self, title: str, x: int, y: int,
                    width: Optional[int] = None, height: Optional[int] = None) -> Dict[str, Any]:
        """Move/resize a window by title using window-manager APIs, not coordinates-on-screen guessing."""
        if not isinstance(title, str) or not title.strip():
            return _outcome("invalid_input", reason="window title must be a non-empty string")
        for value, label in ((x, "x"), (y, "y")):
            if not isinstance(value, int):
                return _outcome("invalid_input", reason=f"{label} must be an integer")
        decision = self._guard("automation.window", f"move {title}")
        if not decision.get("allowed"):
            self._record("move_window", False, "permission denied")
            return _outcome("permission_denied", reason=decision.get("reason"))
        backend, mod = self._window_backend()
        if backend is None:
            return _outcome("unavailable",
                            reason="no window manager backend available on this host")
        try:
            if backend == "pygetwindow":
                matches = [w for w in mod.getAllWindows() if title.lower() in (w.title or "").lower()]
                if not matches:
                    return _outcome("not_found", reason=f"no window matching {title!r}")
                win = matches[0]
                win.moveTo(x, y)
                if width and height:
                    win.resizeTo(int(width), int(height))
                verified = (abs(win.left - x) <= 2 and abs(win.top - y) <= 2)
                self._record("move_window", verified)
                return _outcome("ok" if verified else "failure", backend=backend,
                                window=win.title, position=[win.left, win.top],
                                verified=verified)
            import subprocess
            geom = f"0,{x},{y},{width or -1},{height or -1}"
            proc = subprocess.run(["wmctrl", "-r", title, "-e", geom],
                                  capture_output=True, text=True, timeout=10)
            ok = proc.returncode == 0
            self._record("move_window", ok, proc.stderr.strip())
            return _outcome("ok" if ok else "failure", backend=backend,
                            error=proc.stderr.strip() or None, verified=ok)
        except Exception as exc:
            self._record("move_window", False, str(exc))
            return _outcome("failure", error=f"{type(exc).__name__}: {exc}")

    # ---------------- archives ----------------
    def zip_paths(self, sources: Sequence[str], archive: str,
                  overwrite: bool = False) -> Dict[str, Any]:
        if not sources:
            return _outcome("invalid_input", reason="no source paths given")
        try:
            target = _safe_path(archive, self.allowed_roots)
            resolved = [_safe_path(s, self.allowed_roots) for s in sources]
        except (ValueError, PermissionError) as exc:
            return _outcome("invalid_input" if isinstance(exc, ValueError) else "permission_denied",
                            reason=str(exc))
        missing = [p for p in resolved if not os.path.exists(p)]
        if missing:
            return _outcome("not_found", reason=f"missing sources: {missing}")
        if os.path.exists(target) and not overwrite:
            return _outcome("failure", reason=f"{target} exists; pass overwrite=True to replace")
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        written: List[str] = []
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in resolved:
                    if os.path.isfile(path):
                        zf.write(path, os.path.basename(path))
                        written.append(os.path.basename(path))
                        continue
                    base = os.path.dirname(path.rstrip(os.sep))
                    for root, _dirs, files in os.walk(path):
                        for name in files:
                            full = os.path.join(root, name)
                            rel = os.path.relpath(full, base)
                            zf.write(full, rel)
                            written.append(rel)
        except OSError as exc:
            self._record("zip", False, str(exc))
            return _outcome("failure", error=f"{type(exc).__name__}: {exc}")
        # verification: the archive must open and list what we claimed to add
        with zipfile.ZipFile(target) as zf:
            names = zf.namelist()
        ok = sorted(names) == sorted(written)
        self._record("zip", ok)
        return _outcome("ok" if ok else "failure", archive=target, entries=len(names),
                        verified=ok, members=sorted(names)[:20])

    def unzip(self, archive: str, destination: str) -> Dict[str, Any]:
        try:
            src = _safe_path(archive, self.allowed_roots)
            dest = _safe_path(destination, self.allowed_roots)
        except (ValueError, PermissionError) as exc:
            return _outcome("invalid_input" if isinstance(exc, ValueError) else "permission_denied",
                            reason=str(exc))
        if not os.path.isfile(src):
            return _outcome("not_found", reason=f"{src} is not a file")
        if not zipfile.is_zipfile(src):
            return _outcome("invalid_input", reason=f"{src} is not a zip archive")
        os.makedirs(dest, exist_ok=True)
        extracted: List[str] = []
        try:
            with zipfile.ZipFile(src) as zf:
                members = zf.namelist()
                if len(members) > _ARCHIVE_MEMBER_LIMIT:
                    return _outcome("failure",
                                    reason=f"archive has {len(members)} members, limit is {_ARCHIVE_MEMBER_LIMIT}")
                for member in members:
                    # zip-slip protection: never write outside the destination
                    out_path = os.path.realpath(os.path.join(dest, member))
                    if not (out_path == dest or out_path.startswith(dest + os.sep)):
                        return _outcome("permission_denied",
                                        reason=f"archive member {member!r} escapes the destination")
                zf.extractall(dest)
                extracted = members
        except (OSError, zipfile.BadZipFile) as exc:
            self._record("unzip", False, str(exc))
            return _outcome("failure", error=f"{type(exc).__name__}: {exc}")
        present = [m for m in extracted if os.path.exists(os.path.join(dest, m))]
        ok = len(present) == len(extracted)
        self._record("unzip", ok)
        return _outcome("ok" if ok else "failure", destination=dest,
                        extracted=len(present), verified=ok)

    # ---------------- search ----------------
    def search_computer(self, pattern: str, roots: Optional[Sequence[str]] = None,
                        contains: Optional[str] = None, limit: int = 100,
                        max_bytes: int = 2_000_000) -> Dict[str, Any]:
        """Name-glob search with optional content match. Bounded and skip-on-error."""
        if not isinstance(pattern, str) or not pattern.strip():
            return _outcome("invalid_input", reason="pattern must be a non-empty string")
        limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
        search_roots = list(roots) if roots else (self.allowed_roots or [os.getcwd()])
        hits: List[Dict[str, Any]] = []
        skipped = 0
        for root in search_roots:
            try:
                base = _safe_path(root, self.allowed_roots)
            except (ValueError, PermissionError) as exc:
                return _outcome("permission_denied", reason=str(exc))
            for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: None):
                dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
                for name in filenames:
                    if not fnmatch.fnmatch(name, pattern):
                        continue
                    full = os.path.join(dirpath, name)
                    if contains:
                        try:
                            if os.path.getsize(full) > max_bytes:
                                skipped += 1
                                continue
                            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                                if contains not in fh.read():
                                    continue
                        except OSError:
                            skipped += 1
                            continue
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = None
                    hits.append({"path": full, "size": size})
                    if len(hits) >= limit:
                        self._record("search_computer", True)
                        return _outcome("ok", matches=hits, truncated=True, skipped=skipped)
        self._record("search_computer", True)
        return _outcome("ok", matches=hits, truncated=False, skipped=skipped)

    # ---------------- processes ----------------
    def _process_backend(self) -> str:
        try:
            import psutil  # noqa: F401
            return "psutil"
        except Exception:
            return "proc" if os.path.isdir("/proc") else "none"

    def list_processes(self, name_filter: Optional[str] = None,
                       limit: int = 200) -> Dict[str, Any]:
        backend = self._process_backend()
        procs: List[Dict[str, Any]] = []
        if backend == "psutil":
            import psutil
            for proc in psutil.process_iter(["pid", "name", "username", "status"]):
                try:
                    info = proc.info
                except Exception:
                    continue
                procs.append({"pid": info.get("pid"), "name": info.get("name") or "",
                              "user": info.get("username"), "state": info.get("status")})
        elif backend == "proc":
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/comm", "r", encoding="utf-8") as fh:
                        pname = fh.read().strip()
                except OSError:
                    continue
                procs.append({"pid": int(entry), "name": pname, "user": None, "state": None})
        else:
            return _outcome("unavailable", reason="no process backend (psutil or /proc)")
        if name_filter:
            needle = name_filter.lower()
            procs = [p for p in procs if needle in (p["name"] or "").lower()]
        procs.sort(key=lambda p: p["pid"])
        return _outcome("ok", backend=backend, count=len(procs), processes=procs[:limit])

    def is_critical(self, name: str) -> bool:
        base = os.path.basename((name or "").strip().lower())
        return base in CRITICAL_PROCESSES or base.rstrip("0123456789.") in CRITICAL_PROCESSES

    def kill_process(self, pid: Optional[int] = None, name: Optional[str] = None,
                     force: bool = False, allow_critical: bool = False) -> Dict[str, Any]:
        """Terminate a process after safety checks. Critical/system processes are refused."""
        if pid is None and not name:
            return _outcome("invalid_input", reason="pass pid or name")
        listing = self.list_processes(name_filter=name)
        if not listing["ok"]:
            return listing
        candidates = listing["processes"]
        if pid is not None:
            candidates = [p for p in candidates if p["pid"] == int(pid)]
        if not candidates:
            return _outcome("not_found", reason=f"no process matching pid={pid} name={name!r}")
        target = candidates[0]
        if target["pid"] in (1, os.getpid()):
            return _outcome("permission_denied",
                            reason=f"refusing to kill pid {target['pid']} (init or Jarvis itself)")
        if self.is_critical(target["name"]) and not allow_critical:
            self._record("kill_process", False, "critical process refused")
            return _outcome("permission_denied",
                            reason=f"{target['name']} is a protected system process",
                            process=target)
        decision = self._guard("automation.process.kill", f"kill {target['name']}")
        if not decision.get("allowed"):
            self._record("kill_process", False, "permission denied")
            return _outcome("permission_denied", reason=decision.get("reason"), process=target)
        try:
            os.kill(target["pid"], signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return _outcome("not_found", reason=f"pid {target['pid']} disappeared")
        except PermissionError as exc:
            self._record("kill_process", False, str(exc))
            return _outcome("permission_denied", reason=f"OS refused: {exc}", process=target)
        self._record("kill_process", True)
        return _outcome("ok", process=target, signal="SIGKILL" if force else "SIGTERM")

    # ---------------- manager entry point ----------------
    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """Uniform entry point used by ManagerRegistry.execute_with_fallback."""
        handlers = {
            "move_window": self.move_window, "list_windows": self.list_windows,
            "zip": self.zip_paths, "unzip": self.unzip,
            "search": self.search_computer, "list_processes": self.list_processes,
            "kill_process": self.kill_process, "health": self.health,
        }
        handler = handlers.get(action)
        if handler is None:
            return _outcome("invalid_input", reason=f"unknown automation action {action!r}",
                            supported=sorted(handlers))
        try:
            return handler(**kwargs)
        except TypeError as exc:
            return _outcome("invalid_input", reason=str(exc))


__all__ = ["AutomationManager", "AutomationError", "CRITICAL_PROCESSES"]
