"""Sandboxed file tool.

Every path is resolved and checked against a workspace root, so a command can
never read or write outside it. Used by the tool registry and the coding
manager.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

__all__ = ["FileTool", "file_tool", "SandboxError"]

DEFAULT_ROOT = os.path.abspath(os.environ.get("JARVIS_WORKSPACE", "workspace"))
MAX_READ_BYTES = 2 * 1024 * 1024


class SandboxError(PermissionError):
    """Raised when a path escapes the workspace root."""


class FileTool:
    """Read / write / list / copy / delete inside one directory."""

    name = "file"
    description = "Reads and writes files inside the Jarvis workspace."

    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root or DEFAULT_ROOT)
        os.makedirs(self.root, exist_ok=True)

    # -- safety ------------------------------------------------------
    def resolve(self, path: str) -> str:
        """Absolute path inside the sandbox, or raise SandboxError."""
        candidate = os.path.abspath(os.path.join(self.root, str(path or "")))
        if candidate != self.root and not candidate.startswith(self.root + os.sep):
            raise SandboxError("%r is outside the workspace" % path)
        return candidate

    # -- operations --------------------------------------------------
    def read(self, path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        target = self.resolve(path)
        if not os.path.isfile(target):
            return {"success": False, "error": "no such file: %s" % path}
        if os.path.getsize(target) > MAX_READ_BYTES:
            return {"success": False, "error": "file is too large to read"}
        with open(target, "r", encoding=encoding, errors="replace") as handle:
            return {"success": True, "path": path, "content": handle.read()}

    def write(self, path: str, content: str, append: bool = False) -> Dict[str, Any]:
        target = self.resolve(path)
        os.makedirs(os.path.dirname(target) or self.root, exist_ok=True)
        with open(target, "a" if append else "w", encoding="utf-8") as handle:
            handle.write(str(content))
        return {"success": True, "path": path,
                "bytes": os.path.getsize(target)}

    def list(self, path: str = ".") -> Dict[str, Any]:
        target = self.resolve(path)
        if not os.path.isdir(target):
            return {"success": False, "error": "no such folder: %s" % path}
        entries: List[Dict[str, Any]] = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            entries.append({
                "name": name,
                "type": "folder" if os.path.isdir(full) else "file",
                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
            })
        return {"success": True, "path": path, "entries": entries}

    def delete(self, path: str) -> Dict[str, Any]:
        target = self.resolve(path)
        if os.path.isdir(target):
            shutil.rmtree(target)
        elif os.path.isfile(target):
            os.remove(target)
        else:
            return {"success": False, "error": "no such path: %s" % path}
        return {"success": True, "path": path}

    def copy(self, source: str, destination: str) -> Dict[str, Any]:
        src, dst = self.resolve(source), self.resolve(destination)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst) or self.root, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            return {"success": False, "error": "no such path: %s" % source}
        return {"success": True, "from": source, "to": destination}

    def move(self, source: str, destination: str) -> Dict[str, Any]:
        src, dst = self.resolve(source), self.resolve(destination)
        if not os.path.exists(src):
            return {"success": False, "error": "no such path: %s" % source}
        os.makedirs(os.path.dirname(dst) or self.root, exist_ok=True)
        shutil.move(src, dst)
        return {"success": True, "from": source, "to": destination}

    def exists(self, path: str) -> bool:
        try:
            return os.path.exists(self.resolve(path))
        except SandboxError:
            return False


file_tool = FileTool()
