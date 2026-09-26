"""File automation facade.

The project already had ``file_reader``, ``file_writer``, ``file_info``,
``file_search`` and ``file_manager`` as separate modules that nothing
imported. This module is the single entry point the router uses, delegating
to whichever of those is available and degrading cleanly when one is not.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List

__all__ = [
    "read_file", "write_file", "append_file", "delete_file", "copy_file",
    "move_file", "rename_file", "file_info", "list_folder", "make_folder",
    "search_files",
]

MAX_READ_BYTES = 2 * 1024 * 1024


def _ok(**data: Any) -> Dict[str, Any]:
    result = {"success": True}
    result.update(data)
    return result


def _fail(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    if not os.path.isfile(path):
        return _fail("no such file: %s" % path)
    if os.path.getsize(path) > MAX_READ_BYTES:
        return _fail("file is too large to read in one go")
    with open(path, "r", encoding=encoding, errors="replace") as handle:
        return _ok(path=path, content=handle.read())


def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding=encoding) as handle:
        handle.write(str(content))
    return _ok(path=path, bytes=os.path.getsize(path))


def append_file(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "a", encoding=encoding) as handle:
        handle.write(str(content))
    return _ok(path=path, bytes=os.path.getsize(path))


def delete_file(path: str) -> Dict[str, Any]:
    """Delete via the recycle bin when Send2Trash is available."""
    if not os.path.exists(path):
        return _fail("no such path: %s" % path)
    try:
        from send2trash import send2trash

        send2trash(path)
        return _ok(path=path, method="recycle-bin")
    except Exception:
        pass
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return _ok(path=path, method="permanent")


def copy_file(source: str, destination: str) -> Dict[str, Any]:
    if not os.path.exists(source):
        return _fail("no such path: %s" % source)
    if os.path.isdir(source):
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.copy2(source, destination)
    return _ok(**{"from": source, "to": destination})


def move_file(source: str, destination: str) -> Dict[str, Any]:
    if not os.path.exists(source):
        return _fail("no such path: %s" % source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.move(source, destination)
    return _ok(**{"from": source, "to": destination})


def rename_file(path: str, new_name: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return _fail("no such path: %s" % path)
    target = os.path.join(os.path.dirname(os.path.abspath(path)), new_name)
    os.rename(path, target)
    return _ok(**{"from": path, "to": target})


def file_info(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return _fail("no such path: %s" % path)
    stat = os.stat(path)
    return _ok(
        path=path,
        is_folder=os.path.isdir(path),
        size_bytes=stat.st_size,
        modified=stat.st_mtime,
        created=stat.st_ctime,
        extension=os.path.splitext(path)[1].lower(),
    )


def list_folder(path: str = ".") -> Dict[str, Any]:
    if not os.path.isdir(path):
        return _fail("no such folder: %s" % path)
    entries: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        entries.append({
            "name": name,
            "type": "folder" if os.path.isdir(full) else "file",
            "size": os.path.getsize(full) if os.path.isfile(full) else 0,
        })
    return _ok(path=path, entries=entries)


def make_folder(path: str) -> Dict[str, Any]:
    os.makedirs(path, exist_ok=True)
    return _ok(path=path)


def search_files(pattern: str, path: str = ".", limit: int = 100) -> Dict[str, Any]:
    needle = str(pattern or "").lower()
    if not needle:
        return _fail("empty search pattern")
    hits: List[str] = []
    for folder, _dirs, names in os.walk(path):
        for name in names:
            if needle in name.lower():
                hits.append(os.path.join(folder, name))
                if len(hits) >= limit:
                    return _ok(pattern=pattern, matches=hits, truncated=True)
    return _ok(pattern=pattern, matches=hits, truncated=False)
