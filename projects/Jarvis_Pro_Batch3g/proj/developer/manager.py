"""
Developer Manager — code generation, review, and developer workflow tools.

Capabilities:
  - Code generation from natural language
  - Basic code review / lint hints
  - File scaffolding
  - Git helpers (status, log, branch)
  - Environment info
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from threading import Lock


class DeveloperManager:

    def __init__(self):
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Environment info
    # ------------------------------------------------------------------

    def environment(self) -> dict:
        """Return a snapshot of the current environment."""
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "cwd": os.getcwd(),
            "path_dirs": len(os.environ.get("PATH", "").split(os.pathsep)),
        }

    def installed_packages(self) -> list:
        """Return a list of pip-installed packages."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True, timeout=30)
            return result.stdout.strip().splitlines()
        except Exception as e:
            return [f"Error: {e}"]

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def git_status(self, repo_path: str = ".") -> dict:
        """Return git status for a repo."""
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_path, capture_output=True, text=True, timeout=10)
            return {
                "success": True,
                "output": result.stdout.strip(),
                "changed_files": result.stdout.count("\n") + (1 if result.stdout.strip() else 0),
            }
        except FileNotFoundError:
            return {"success": False, "error": "git not found on PATH"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def git_log(self, repo_path: str = ".", limit: int = 10) -> dict:
        """Return recent git commits."""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{limit}"],
                cwd=repo_path, capture_output=True, text=True, timeout=10)
            return {
                "success": True,
                "commits": result.stdout.strip().splitlines(),
            }
        except FileNotFoundError:
            return {"success": False, "error": "git not found on PATH"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def git_branch(self, repo_path: str = ".") -> dict:
        """Return current branch name."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path, capture_output=True, text=True, timeout=10)
            return {
                "success": True,
                "branch": result.stdout.strip(),
            }
        except FileNotFoundError:
            return {"success": False, "error": "git not found on PATH"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # File scaffolding
    # ------------------------------------------------------------------

    def scaffold_file(self, path: str, content: str = "") -> dict:
        """Create a file with optional content."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scaffold_python_script(self, path: str, name: str,
                               description: str = "") -> dict:
        """Create a basic Python script with a docstring."""
        desc = description or name
        content = (
            '"""{desc}"""\n'
            '\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'
        ).format(desc=desc)
        return self.scaffold_file(path, content)

    # ------------------------------------------------------------------
    # Code analysis helpers
    # ------------------------------------------------------------------

    def count_lines(self, path: str, extensions: list = None) -> dict:
        """Count lines of code in a directory or file."""
        extensions = extensions or [".py", ".js", ".ts", ".java",
                                   ".cpp", ".c", ".go", ".rs", ".rb"]
        total = 0
        files = 0

        try:
            p = Path(path)
            if p.is_file():
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                return {"total_lines": len(lines), "files": 1, "path": str(p)}
            for file_path in p.rglob("*"):
                if file_path.is_file() and file_path.suffix in extensions:
                    try:
                        lines = file_path.read_text(
                            encoding="utf-8", errors="ignore").splitlines()
                        total += len(lines)
                        files += 1
                    except Exception:
                        pass
            return {"total_lines": total, "files": files, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}


_manager = DeveloperManager()

environment = _manager.environment
installed_packages = _manager.installed_packages
git_status = _manager.git_status
git_log = _manager.git_log
git_branch = _manager.git_branch
scaffold_file = _manager.scaffold_file
scaffold_python_script = _manager.scaffold_python_script
count_lines = _manager.count_lines
