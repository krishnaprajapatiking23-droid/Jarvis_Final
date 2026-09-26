"""One-command installer for this JARVIS PRO build.

Why this file exists
--------------------
Copying the build by hand kept going wrong: the extracted folder gets a
name like ``Jarvis_Pro_conversation_system (3)``, the copy command was
pointed at a folder that did not exist, and the project folder was left
as a mix of old and new files.  A half-applied build produces exactly
the symptoms that looked like bugs: identical greetings, provider
signature errors, missing tools, failing tests.

Run this file from wherever it happens to sit - it copies *its own
folder* into the project, so the source path can never be wrong.

    python install_to_project.py "C:\\Users\\Yogi\\OneDrive\\Desktop\\Jarvis_Pro"

It then verifies the result, so you know immediately whether the
project folder is now the complete new build.

What is protected
-----------------
* Databases (``*.db``) and learned memory files are never overwritten.
* ``config/settings.json`` keeps your values; only missing keys are
  added.
* Everything else (code, tests, tools) is replaced with this build.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent

DEFAULT_TARGET = Path(r"C:\Users\Yogi\OneDrive\Desktop\Jarvis_Pro")

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".idea", ".vscode"}

# Files that belong to the running assistant, not to the build.
KEEP_SUFFIXES = {".db", ".db-journal", ".sqlite", ".sqlite3", ".log"}
KEEP_NAMES = {
    "owner.json",
    "memory.json",
    "semantic_memory.json",
    "dialogue_rotation.json",
}

MERGE_FILES = {"config/settings.json"}


def relative_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_DIRS:
            continue
        if path.suffix == ".pyc":
            continue
        yield path.relative_to(root)


def merge_settings(source: Path, target: Path) -> str:
    """Add new keys to the existing settings file without losing values."""
    try:
        with source.open("r", encoding="utf-8") as handle:
            fresh = json.load(handle)
    except Exception:
        return "skipped (unreadable source)"

    current = {}
    if target.exists():
        try:
            with target.open("r", encoding="utf-8") as handle:
                current = json.load(handle)
        except Exception:
            current = {}

    added = [key for key in fresh if key not in current]
    if not added and target.exists():
        return "kept (already complete)"

    merged = dict(fresh)
    merged.update(current)

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=4)
        handle.write("\n")

    if not added:
        return "written"
    return "added keys: " + ", ".join(added)


def install(target: Path) -> int:
    if not (SOURCE / "conversation" / "dialogue_manager.py").exists():
        print("This script is not sitting inside a JARVIS build folder.")
        print("Source checked:", SOURCE)
        return 1

    if SOURCE == target:
        print("Source and target are the same folder; nothing to do.")
        return 0

    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    protected = 0
    settings_note = ""

    for relative in relative_files(SOURCE):
        posix = relative.as_posix()

        destination = target / relative

        if posix in MERGE_FILES:
            settings_note = merge_settings(SOURCE / relative, destination)
            continue

        if destination.exists() and (
            destination.suffix in KEEP_SUFFIXES or destination.name in KEEP_NAMES
        ):
            protected += 1
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / relative, destination)
        copied += 1

    print("=" * 68)
    print("JARVIS PRO - install")
    print("=" * 68)
    print("source        :", SOURCE)
    print("target        :", target)
    print("files copied  :", copied)
    print("files kept    :", protected, "(your databases and memory)")
    if settings_note:
        print("settings.json :", settings_note)
    print()

    verifier = target / "tools" / "verify_build.py"
    if not verifier.exists():
        print("verify_build.py did not arrive - the copy did not finish.")
        return 1

    sys.path.insert(0, str(target))
    print("Verifying the installed build...")
    print()

    code = compile(verifier.read_text(encoding="utf-8"), str(verifier), "exec")
    namespace = {"__file__": str(verifier), "__name__": "verify_build"}
    exec(code, namespace)
    result = namespace["main"]()

    if result == 0:
        print()
        print("Next:")
        print("  cd", target)
        print("  python tools\\run_tests.py")
        print("  python tools\\try_variation.py --chat")

    return int(result)


def main() -> int:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).expanduser()
    elif DEFAULT_TARGET.exists():
        target = DEFAULT_TARGET
    else:
        print("Usage: python install_to_project.py <path to your Jarvis_Pro folder>")
        return 1

    return install(target.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
