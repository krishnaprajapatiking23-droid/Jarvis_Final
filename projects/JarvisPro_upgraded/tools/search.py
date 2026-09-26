"""Local search tool.

Searches the workspace for filenames and file contents. Deliberately local
only: no network call is made, so it works offline and cannot leak data.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from tools.file_tool import DEFAULT_ROOT, SandboxError, FileTool

__all__ = ["SearchTool", "search_tool"]

TEXT_SUFFIXES = {
    ".txt", ".md", ".py", ".json", ".yaml", ".yml", ".ini", ".cfg",
    ".csv", ".html", ".css", ".js", ".ts", ".sh", ".toml", ".log",
}
MAX_MATCHES = 100
MAX_FILE_BYTES = 1024 * 1024


class SearchTool:
    """Filename and content search inside the workspace."""

    name = "search"
    description = "Finds files by name or by the text inside them."

    def __init__(self, root: Optional[str] = None):
        self.files = FileTool(root or DEFAULT_ROOT)

    def by_name(self, pattern: str, path: str = ".") -> List[str]:
        needle = str(pattern or "").lower()
        if not needle:
            return []
        root = self.files.resolve(path)
        hits: List[str] = []
        for folder, _dirs, names in os.walk(root):
            for name in names:
                if needle in name.lower():
                    hits.append(os.path.relpath(os.path.join(folder, name),
                                                self.files.root))
                    if len(hits) >= MAX_MATCHES:
                        return hits
        return hits

    def by_content(self, pattern: str, path: str = ".",
                   regex: bool = False) -> List[Dict[str, Any]]:
        if not pattern:
            return []
        matcher = (re.compile(pattern, re.IGNORECASE) if regex
                   else re.compile(re.escape(pattern), re.IGNORECASE))
        root = self.files.resolve(path)
        hits: List[Dict[str, Any]] = []

        for folder, _dirs, names in os.walk(root):
            for name in names:
                if os.path.splitext(name)[1].lower() not in TEXT_SUFFIXES:
                    continue
                full = os.path.join(folder, name)
                try:
                    if os.path.getsize(full) > MAX_FILE_BYTES:
                        continue
                    with open(full, "r", encoding="utf-8", errors="replace") as handle:
                        for number, line in enumerate(handle, start=1):
                            if matcher.search(line):
                                hits.append({
                                    "file": os.path.relpath(full, self.files.root),
                                    "line": number,
                                    "text": line.rstrip()[:200],
                                })
                                if len(hits) >= MAX_MATCHES:
                                    return hits
                except OSError:
                    continue
        return hits

    def execute(self, query: str, path: str = ".") -> Dict[str, Any]:
        return {
            "success": True,
            "query": query,
            "filenames": self.by_name(query, path),
            "contents": self.by_content(query, path),
        }


search_tool = SearchTool()
