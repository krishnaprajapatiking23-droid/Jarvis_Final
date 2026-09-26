from brains_v2.llm.manager import ask
import os
import sys

def process(command):
    """
    Coding Manager
    Handles coding-related commands.
    """

    command = command.strip()

    if not command:
        return None

    text = command.lower()

    # Git branch management
    if (
        text == "git branch"
        or text == "git current branch"
        or text.startswith("git create branch ")
        or text.startswith("git switch branch ")
    ):
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())

            if text == "git branch":
                git_command = [
                    "git",
                    "branch"
                ]

            elif text == "git current branch":
                git_command = [
                    "git",
                    "branch",
                    "--show-current"
                ]

            elif text.startswith("git create branch "):
                branch_name = command[
                    len("git create branch "):
                ].strip()

                if not branch_name:
                    return {
                        "reply": "Please specify a branch name.",
                        "type": "coding"
                    }

                git_command = [
                    "git",
                    "branch",
                    branch_name
                ]

            else:
                branch_name = command[
                    len("git switch branch "):
                ].strip()

                if not branch_name:
                    return {
                        "reply": "Please specify a branch name.",
                        "type": "coding"
                    }

                git_command = [
                    "git",
                    "switch",
                    branch_name
                ]

            result = subprocess.run(
                git_command,
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30
            )

            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown Git error."
                )

                return {
                    "reply": (
                        "Git branch operation failed.\n\n"
                        f"{error}"
                    ),
                    "type": "coding",
                    "git_branch_operation": text
                }

            output = (
                result.stdout.strip()
                or "Operation completed successfully."
            )

            return {
                "reply": (
                    "Git branch operation completed successfully.\n\n"
                    f"{output}"
                ),
                "type": "coding",
                "git_branch_operation": text,
                "git_output": output
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Git is not installed or is not available "
                    "in the system PATH."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Git branch operation exceeded "
                    "the 30-second time limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Git branch management failed: {e}",
                "type": "coding"
            }

    # Generate Git commit message
    if (
        text == "generate commit"
        or text == "generate commit message"
        or text == "suggest commit message"
    ):
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())

            result = subprocess.run(
                ["git", "diff", "--no-ext-diff"],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30
            )

            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown Git error."
                )

                return {
                    "reply": (
                        "Unable to read Git changes.\n\n"
                        f"{error}"
                    ),
                    "type": "coding"
                }

            diff = result.stdout.strip()

            if not diff:
                return {
                    "reply": (
                        "No unstaged changes were found. "
                        "There is nothing to generate a commit message for."
                    ),
                    "type": "coding",
                    "commit_message": None
                }

            changed_files = []

            for line in diff.splitlines():

                if line.startswith("+++ b/"):

                    filename = line[6:].strip()

                    if filename != "/dev/null":
                        changed_files.append(filename)

            changed_files = list(
                dict.fromkeys(changed_files)
            )

            diff_lower = diff.lower()

            if (
                "test" in diff_lower
                or "pytest" in diff_lower
            ):
                commit_message = "test: improve project tests"

            elif (
                "coding_manager.py" in diff
                or "coding manager" in diff_lower
            ):
                commit_message = "feat: improve coding manager"

            elif (
                "brains_v2" in diff
                and "manager" in diff_lower
            ):
                commit_message = "feat: improve Brain V2 manager"

            elif (
                "fix" in diff_lower
                or "bug" in diff_lower
                or "error" in diff_lower
            ):
                commit_message = "fix: improve project functionality"

            else:
                commit_message = "chore: update project files"

            return {
                "reply": (
                    "Commit message generated successfully.\n\n"
                    f"Suggested commit message:\n"
                    f"{commit_message}\n\n"
                    f"Changed files detected: {len(changed_files)}"
                ),
                "type": "coding",
                "commit_message": commit_message,
                "changed_files": changed_files
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Git is not installed or is not available "
                    "in the system PATH."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Commit message generation exceeded "
                    "the 30-second time limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Commit generation failed: {e}",
                "type": "coding"
            }

    # Review Git diff
    if (
        text == "review diff"
        or text == "diff review"
        or text == "review git diff"
        or text == "analyze diff"
    ):
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())

            result = subprocess.run(
                ["git", "diff", "--no-ext-diff"],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30
            )

            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown Git error."
                )

                return {
                    "reply": (
                        "Diff review failed.\n\n"
                        f"{error}"
                    ),
                    "type": "coding"
                }

            diff = result.stdout.strip()

            if not diff:
                return {
                    "reply": (
                        "Diff review completed.\n\n"
                        "No unstaged changes were found."
                    ),
                    "type": "coding",
                    "diff_review": {
                        "changed_files": [],
                        "insertions": 0,
                        "deletions": 0,
                        "risk_level": "Low"
                    }
                }

            changed_files = []
            insertions = 0
            deletions = 0

            for line in diff.splitlines():

                if line.startswith("+++ b/"):
                    filename = line[6:].strip()

                    if filename != "/dev/null":
                        changed_files.append(filename)

                elif line.startswith("+") and not line.startswith("+++"):
                    insertions += 1

                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1

            changed_files = list(
                dict.fromkeys(changed_files)
            )

            diff_lower = diff.lower()

            risk_keywords = [
                "password",
                "secret",
                "token",
                "api_key",
                "subprocess",
                "os.system",
                "eval(",
                "exec(",
                "shell=true"
            ]

            detected_risks = []

            for keyword in risk_keywords:

                if keyword.lower() in diff_lower:
                    detected_risks.append(keyword)

            if detected_risks:
                risk_level = "High"

            elif (
                insertions + deletions >= 200
                or len(changed_files) >= 10
            ):
                risk_level = "Medium"

            else:
                risk_level = "Low"

            risk_text = (
                "\n".join(
                    f"- {item}"
                    for item in detected_risks
                )
                if detected_risks
                else "None detected."
            )

            file_text = (
                "\n".join(
                    f"- {item}"
                    for item in changed_files
                )
                if changed_files
                else "No files detected."
            )

            return {
                "reply": (
                    "Git diff review completed successfully.\n\n"
                    f"Risk level: {risk_level}\n"
                    f"Changed files: {len(changed_files)}\n"
                    f"Insertions: {insertions}\n"
                    f"Deletions: {deletions}\n\n"
                    f"Changed files:\n{file_text}\n\n"
                    f"Potential risk indicators:\n{risk_text}"
                ),
                "type": "coding",
                "diff_review": {
                    "changed_files": changed_files,
                    "insertions": insertions,
                    "deletions": deletions,
                    "risk_level": risk_level,
                    "risk_indicators": detected_risks
                }
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Git is not installed or is not available "
                    "in the system PATH."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Diff review exceeded the "
                    "30-second time limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Diff review failed: {e}",
                "type": "coding"
            }

    # Apply Git patch
    if (
        text.startswith("apply patch ")
        or text.startswith("git apply patch ")
    ):
        try:
            import subprocess

            if text.startswith("apply patch "):
                patch_file = command[len("apply patch "):].strip()
            else:
                patch_file = command[len("git apply patch "):].strip()

            if not patch_file:
                return {
                    "reply": "Please specify a patch file.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            patch_path = os.path.abspath(
                os.path.join(project_path, patch_file)
            )

            if (
                os.path.commonpath(
                    [project_path, patch_path]
                ) != project_path
            ):
                return {
                    "reply": "Patch file must be inside the project.",
                    "type": "coding"
                }

            if not os.path.isfile(patch_path):
                return {
                    "reply": (
                        f"Patch file not found: {patch_file}"
                    ),
                    "type": "coding"
                }

            result = subprocess.run(
                ["git", "apply", patch_path],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30
            )

            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown Git patch error."
                )

                return {
                    "reply": (
                        "Patch application failed.\n\n"
                        f"{error}"
                    ),
                    "type": "coding",
                    "patch_file": patch_file,
                    "patch_applied": False
                }

            return {
                "reply": (
                    "Patch applied successfully.\n\n"
                    f"Patch: {patch_file}"
                ),
                "type": "coding",
                "patch_file": patch_file,
                "patch_applied": True
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Git is not installed or is not available "
                    "in the system PATH."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Patch application exceeded "
                    "the 30-second time limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Patch application failed: {e}",
                "type": "coding"
            }

    # GitHub integration
    if text in {
        "github status",
        "github repo",
        "github repository"
    }:
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())

            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15
            )

            if result.returncode != 0:
                return {
                    "reply": (
                        "No GitHub origin remote is configured."
                    ),
                    "type": "coding",
                    "github_connected": False
                }

            remote_url = result.stdout.strip()

            if "github.com" not in remote_url.lower():
                return {
                    "reply": (
                        "The origin remote is not a GitHub repository."
                    ),
                    "type": "coding",
                    "github_connected": False,
                    "remote_url": remote_url
                }

            return {
                "reply": (
                    "GitHub repository connected successfully.\n\n"
                    f"Remote: {remote_url}"
                ),
                "type": "coding",
                "github_connected": True,
                "remote_url": remote_url
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": "GitHub status check timed out.",
                "type": "coding",
                "github_connected": False
            }

        except Exception as e:
            return {
                "reply": f"GitHub status check failed: {e}",
                "type": "coding",
                "github_connected": False
            }

    # Documentation generation
    if (
        text == "generate documentation"
        or text == "generate docs"
    ):
        try:
            import ast

            project_path = os.path.abspath(os.getcwd())
            documented = []
            functions = 0
            classes = 0

            for root, dirs, files in os.walk(project_path):
                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        ".venv",
                        "venv",
                        "__pycache__"
                    }
                ]

                for filename in files:
                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8"
                        ) as f:
                            source = f.read()

                        tree = ast.parse(source)

                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):
                                functions += 1
                                if ast.get_docstring(node):
                                    documented.append(
                                        f"{filename}:{node.lineno} "
                                        f"function {node.name}"
                                    )

                            elif isinstance(node, ast.ClassDef):
                                classes += 1
                                if ast.get_docstring(node):
                                    documented.append(
                                        f"{filename}:{node.lineno} "
                                        f"class {node.name}"
                                    )

                    except (SyntaxError, UnicodeDecodeError):
                        continue

            report_path = os.path.join(
                project_path,
                "DOCUMENTATION_REPORT.md"
            )

            with open(
                report_path,
                "w",
                encoding="utf-8"
            ) as f:
                f.write("# Project Documentation Report\n\n")
                f.write(
                    f"- Python functions: {functions}\n"
                )
                f.write(
                    f"- Python classes: {classes}\n"
                )
                f.write(
                    f"- Existing docstrings: "
                    f"{len(documented)}\n\n"
                )
                f.write("## Documented Symbols\n\n")

                if documented:
                    for item in documented:
                        f.write(f"- {item}\n")
                else:
                    f.write(
                        "No existing docstrings were found.\n"
                    )

            return {
                "reply": (
                    "Documentation report generated successfully.\n\n"
                    f"File: {report_path}"
                ),
                "type": "coding",
                "documentation_generated": True,
                "documentation_file": report_path
            }

        except Exception as e:
            return {
                "reply": (
                    f"Documentation generation failed: {e}"
                ),
                "type": "coding",
                "documentation_generated": False
            }

    # Test coverage
    if (
        text.startswith("test coverage ")
        or text.startswith("coverage ")
        or text.startswith("run coverage ")
    ):
        try:
            import subprocess

            if text.startswith("test coverage "):
                target = command[len("test coverage "):].strip()
            elif text.startswith("run coverage "):
                target = command[len("run coverage "):].strip()
            else:
                target = command[len("coverage "):].strip()

            if not target:
                target = "."

            project_path = os.path.abspath(os.getcwd())

            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "pytest",
                    target,
                    "--cov",
                    "--cov-report=term-missing"
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )

            output = (
                result.stdout.strip()
                or result.stderr.strip()
                or "No coverage output was produced."
            )

            if result.returncode == 0:
                return {
                    "reply": (
                        "Test coverage completed successfully.\n\n"
                        f"{output}"
                    ),
                    "type": "coding",
                    "test_coverage": True
                }

            return {
                "reply": (
                    "Test coverage completed with test or coverage "
                    "issues.\n\n"
                    f"{output}"
                ),
                "type": "coding",
                "test_coverage": False
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Test coverage exceeded the "
                    "120-second time limit."
                ),
                "type": "coding",
                "test_coverage": False
            }

        except Exception as e:
            return {
                "reply": f"Test coverage failed: {e}",
                "type": "coding",
                "test_coverage": False
            }

    # Git operations

    if (
        text == "git status"
        or text == "git log"
        or text == "git diff"
    ):
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())

            git_command = {
                "git status": ["git", "status", "--short", "--branch"],
                "git log": [
                    "git",
                    "log",
                    "--oneline",
                    "-10"
                ],
                "git diff": ["git", "diff"]
            }[text]

            result = subprocess.run(
                git_command,
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30
            )

            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown Git error."
                )

                return {
                    "reply": (
                        f"Git operation failed.\n\n"
                        f"{error}"
                    ),
                    "type": "coding",
                    "git_operation": text
                }

            output = (
                result.stdout.strip()
                or "No changes or output."
            )

            return {
                "reply": (
                    f"Git {text[4:]} completed successfully.\n\n"
                    f"{output}"
                ),
                "type": "coding",
                "git_operation": text,
                "git_output": output
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Git is not installed or is not available "
                    "in the system PATH."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Git operation exceeded the "
                    "30-second time limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Git operation failed: {e}",
                "type": "coding"
            }

    # Detect Python and system environment
    if (
        text == "detect environment"
        or text == "check environment"
        or text == "environment info"
        or text == "show environment"
    ):
        try:
            import platform

            project_path = os.path.abspath(os.getcwd())

            virtual_env = (
                os.environ.get("VIRTUAL_ENV")
                or os.environ.get("CONDA_PREFIX")
            )

            environment_info = {
                "python_version": platform.python_version(),
                "python_executable": sys.executable,
                "os": platform.system(),
                "os_version": platform.version(),
                "platform": platform.platform(),
                "project_path": project_path,
                "virtual_environment": virtual_env or "None"
            }

            return {
                "reply": (
                    "Environment detected successfully.\n\n"
                    f"Python: {environment_info['python_version']}\n"
                    f"Python executable: {environment_info['python_executable']}\n"
                    f"OS: {environment_info['os']}\n"
                    f"OS version: {environment_info['os_version']}\n"
                    f"Platform: {environment_info['platform']}\n"
                    f"Project path: {environment_info['project_path']}\n"
                    f"Virtual environment: "
                    f"{environment_info['virtual_environment']}"
                ),
                "type": "coding",
                "environment": environment_info
            }

        except Exception as e:
            return {
                "reply": f"Environment detection failed: {e}",
                "type": "coding"
            }

    # Manage Python virtual environments
    if (
        text == "create virtual environment"
        or text == "create venv"
        or text == "check virtual environment"
    ):
        try:
            import subprocess

            project_path = os.path.abspath(os.getcwd())
            venv_path = os.path.join(project_path, ".venv")

            # Check virtual environment
            if text == "check virtual environment":
                if os.path.isdir(venv_path):
                    return {
                        "reply": (
                            "Virtual environment exists.\n\n"
                            f"Location: {venv_path}"
                        ),
                        "type": "coding",
                        "virtual_environment": venv_path
                    }

                return {
                    "reply": "No project virtual environment was found.",
                    "type": "coding",
                    "virtual_environment": None
                }

            # Prevent accidental overwrite
            if os.path.exists(venv_path):
                return {
                    "reply": (
                        "Virtual environment already exists.\n\n"
                        f"Location: {venv_path}"
                    ),
                    "type": "coding",
                    "virtual_environment": venv_path
                }

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "venv",
                    venv_path
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )

            if result.returncode != 0:
                output = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Unknown virtual environment error."
                )

                return {
                    "reply": (
                        "Virtual environment creation failed.\n\n"
                        f"{output}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    "Virtual environment created successfully.\n\n"
                    f"Location: {venv_path}"
                ),
                "type": "coding",
                "virtual_environment": venv_path
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Virtual environment creation exceeded "
                    "the 120-second limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Virtual environment management failed: {e}",
                "type": "coding"
            }

    # Fix Python lint issues with Ruff
    if (
        text.startswith("fix lint ")
        or text.startswith("fix linting ")
    ):
        try:
            if text.startswith("fix lint "):
                filename = command[len("fix lint "):].strip()
            else:
                filename = command[len("fix linting "):].strip()

            if not filename:
                return {
                    "reply": "Please specify a Python file to fix.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only fix files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Lint fixing currently supports Python files only.",
                    "type": "coding"
                }

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    file_path,
                    "--fix"
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            output = (
                result.stdout.strip()
                or result.stderr.strip()
            )

            if result.returncode != 0:
                return {
                    "reply": (
                        f"Lint fixing completed with remaining issues "
                        f"in {filename}.\n\n"
                        f"{output or 'Ruff reported remaining issues.'}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully fixed lint issues in {filename}.\n\n"
                    f"{output or 'No remaining lint issues.'}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Lint fixing failed: {e}",
                "type": "coding"
            }

    # Lint Python code with Ruff
    if (
        text.startswith("lint ")
        or text.startswith("lint code in ")
        or text.startswith("run ruff on ")
    ):
        try:
            if text.startswith("lint code in "):
                filename = command[len("lint code in "):].strip()
            elif text.startswith("run ruff on "):
                filename = command[len("run ruff on "):].strip()
            else:
                filename = command[len("lint "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the Python file to lint.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only lint files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Linting currently supports Python files only.",
                    "type": "coding"
                }

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    file_path
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = (
                result.stdout.strip()
                or result.stderr.strip()
            )

            if result.returncode == 0:
                return {
                    "reply": (
                        f"Lint check passed for {filename}.\n\n"
                        + (output or "No lint issues found.")
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Lint check found issues in {filename}.\n\n"
                    + (output or "Ruff reported linting issues.")
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": "Linting exceeded the 120-second limit.",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Linting failed: {e}",
                "type": "coding"
            }

    # Security scan Python code with Bandit
    if (
        text.startswith("security scan ")
        or text.startswith("security check ")
        or text.startswith("scan security in ")
        or text.startswith("run bandit on ")
    ):
        try:
            if text.startswith("security scan "):
                filename = command[len("security scan "):].strip()
            elif text.startswith("security check "):
                filename = command[len("security check "):].strip()
            elif text.startswith("scan security in "):
                filename = command[len("scan security in "):].strip()
            else:
                filename = command[len("run bandit on "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the Python file to security-scan.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": (
                        "I can only security-scan files "
                        "inside the Jarvis project."
                    ),
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": (
                        "Security scanning currently supports "
                        "Python files only."
                    ),
                    "type": "coding"
                }

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bandit",
                    "-q",
                    file_path
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = (
                result.stdout.strip()
                or result.stderr.strip()
            )

            if result.returncode == 0:
                return {
                    "reply": (
                        f"Security scan passed for {filename}.\n\n"
                        + (
                            output
                            or "No security issues were detected."
                        )
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Security scan found issues in {filename}.\n\n"
                    + (
                        output
                        or "Bandit reported security findings."
                    )
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": (
                    "Security scanning exceeded "
                    "the 120-second limit."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Security scan failed: {e}",
                "type": "coding"
            }

    # Type-check Python code with mypy
    if (
        text.startswith("type check ")
        or text.startswith("check types in ")
        or text.startswith("run mypy on ")
    ):
        try:
            if text.startswith("type check "):
                filename = command[len("type check "):].strip()
            elif text.startswith("check types in "):
                filename = command[len("check types in "):].strip()
            else:
                filename = command[len("run mypy on "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the Python file to type-check.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only type-check files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Type checking currently supports Python files only.",
                    "type": "coding"
                }

            import subprocess

            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "mypy",
                    file_path,
                    "--no-error-summary"
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = (
                result.stdout.strip()
                or result.stderr.strip()
            )

            if result.returncode == 0:
                return {
                    "reply": (
                        f"Type check passed for {filename}.\n\n"
                        + (output or "No type errors found.")
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Type check found issues in {filename}.\n\n"
                    + (output or "Mypy reported type-checking errors.")
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": "Type checking exceeded the 120-second limit.",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Type checking failed: {e}",
                "type": "coding"
            }

    # Analyze Python project dependencies
    if (
        text == "analyze dependencies"
        or text == "dependency analysis"
        or text == "analyze project dependencies"
        or text.startswith("dependencies of ")
        or text.startswith("dependents of ")
        or text.startswith("impact analysis of ")
    ):
        try:
            import ast

            project_path = os.path.abspath(os.getcwd())
            dependency_map = {}

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules",
                        "build",
                        "dist"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    relative_path = os.path.relpath(
                        file_path,
                        project_path
                    )

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8"
                        ) as file:
                            source_code = file.read()

                        tree = ast.parse(
                            source_code,
                            filename=relative_path
                        )

                    except (
                        OSError,
                        SyntaxError,
                        UnicodeDecodeError
                    ):
                        continue

                    imports = []

                    for node in ast.walk(tree):

                        if isinstance(node, ast.Import):

                            for alias in node.names:
                                imports.append(alias.name)

                        elif isinstance(node, ast.ImportFrom):

                            if node.module:
                                imports.append(node.module)

                    dependency_map[relative_path] = sorted(
                        set(imports)
                    )

            # Specific file dependency query

            # Impact analysis
            if text.startswith("impact analysis of "):

                filename = command[
                    len("impact analysis of "):
                ].strip()

                requested_path = (
                    filename
                    .replace("\\", "/")
                    .strip("/")
                    .lower()
                )

                matching_file = None

                for path in dependency_map:

                    indexed_path = (
                        path
                        .replace("\\", "/")
                        .strip("/")
                        .lower()
                    )

                    if indexed_path == requested_path:
                        matching_file = path
                        break

                if matching_file is None:

                    return {
                        "reply": (
                            f"File not found in dependency index: "
                            f"{filename}"
                        ),
                        "type": "coding"
                    }

                direct_dependencies = dependency_map[
                    matching_file
                ]

                target_module = os.path.splitext(
                    matching_file.replace("\\", "/")
                )[0].replace("/", ".")

                direct_dependents = []

                for source_file, imports in dependency_map.items():

                    for imported_module in imports:

                        normalized_import = (
                            imported_module.strip()
                        )

                        if (
                            normalized_import == target_module
                            or normalized_import.startswith(
                                target_module + "."
                            )
                        ):
                            direct_dependents.append(
                                source_file
                            )
                            break

                impact_level = "Low"

                if len(direct_dependents) >= 10:
                    impact_level = "High"

                elif len(direct_dependents) >= 3:
                    impact_level = "Medium"

                dependency_text = (
                    "\n".join(
                        f"- {item}"
                        for item in direct_dependencies
                    )
                    if direct_dependencies
                    else "None detected."
                )

                dependent_text = (
                    "\n".join(
                        f"- {item}"
                        for item in direct_dependents
                    )
                    if direct_dependents
                    else "None detected."
                )

                return {
                    "reply": (
                        f"Impact analysis for "
                        f"{matching_file}:\n\n"
                        f"Impact level: {impact_level}\n\n"
                        f"Direct dependencies:\n"
                        f"{dependency_text}\n\n"
                        f"Direct dependents:\n"
                        f"{dependent_text}\n\n"
                        f"Potentially affected files: "
                        f"{len(direct_dependents)}"
                    ),
                    "type": "coding",
                    "impact_level": impact_level,
                    "dependencies": direct_dependencies,
                    "dependents": direct_dependents
                }

            # Reverse dependency query
            if text.startswith("dependents of "):

                filename = command[
                    len("dependents of "):
                ].strip()

                requested_path = (
                    filename
                    .replace("\\", "/")
                    .strip("/")
                    .lower()
                )

                matching_file = None

                for path in dependency_map:

                    indexed_path = (
                        path
                        .replace("\\", "/")
                        .strip("/")
                        .lower()
                    )

                    if indexed_path == requested_path:
                        matching_file = path
                        break

                if matching_file is None:

                    return {
                        "reply": (
                            f"File not found in dependency index: "
                            f"{filename}"
                        ),
                        "type": "coding",
                        "dependents": []
                    }

                target_module = os.path.splitext(
                    matching_file.replace("\\", "/")
                )[0].replace("/", ".")

                dependents = []

                for source_file, imports in dependency_map.items():

                    for imported_module in imports:

                        normalized_import = imported_module.strip()

                        if (
                            normalized_import == target_module
                            or normalized_import.startswith(
                                target_module + "."
                            )
                        ):
                            dependents.append(source_file)
                            break

                return {
                    "reply": (
                        f"Dependents of {matching_file}:\n\n"
                        + (
                            "\n".join(
                                f"- {item}"
                                for item in dependents
                            )
                            if dependents
                            else "No dependent files found."
                        )
                    ),
                    "type": "coding",
                    "dependents": dependents
                }

            if text.startswith("dependencies of "):

                filename = command[
                    len("dependencies of "):
                ].strip()

                matching_file = None

                requested_path = os.path.normcase(
                    os.path.normpath(filename)
                ).replace("\\", "/").strip("/")

                for path in dependency_map:

                    indexed_path = os.path.normcase(
                        os.path.normpath(path)
                    ).replace("\\", "/").strip("/")

                    if indexed_path == requested_path:
                        matching_file = path
                        break

                # Fallback: compare absolute paths
                if matching_file is None:

                    requested_absolute = os.path.abspath(
                        os.path.join(
                            project_path,
                            filename
                        )
                    )

                    requested_absolute = os.path.normcase(
                        os.path.normpath(requested_absolute)
                    )

                    for path in dependency_map:

                        indexed_absolute = os.path.normcase(
                            os.path.normpath(
                                os.path.join(
                                    project_path,
                                    path
                                )
                            )
                        )

                        if indexed_absolute == requested_absolute:
                            matching_file = path
                            break

                if matching_file is None:
                    return {
                        "reply": f"File not found in dependency index: {filename}",
                        "type": "coding"
                    }

                dependencies = dependency_map[matching_file]

                if dependencies:
                    dependency_text = "\n".join(
                        f"- {item}"
                        for item in dependencies
                    )
                else:
                    dependency_text = "No imports found."

                return {
                    "reply": (
                        f"Dependencies of {matching_file}:\n\n"
                        f"{dependency_text}"
                    ),
                    "type": "coding",
                    "dependencies": dependencies
                }

            total_dependencies = sum(
                len(items)
                for items in dependency_map.values()
            )

            return {
                "reply": (
                    "Dependency analysis completed successfully.\n\n"
                    f"Python files analyzed: {len(dependency_map)}\n"
                    f"Import relationships found: "
                    f"{total_dependencies}"
                ),
                "type": "coding",
                "dependencies": dependency_map
            }

        except Exception as e:
            return {
                "reply": f"Dependency analysis failed: {e}",
                "type": "coding"
            }

    # Build project architecture graph
    if (
        text == "architecture graph"
        or text == "show architecture graph"
        or text == "build architecture graph"
        or text == "project architecture graph"
    ):
        try:
            import ast

            project_path = os.path.abspath(os.getcwd())
            graph = {
                "nodes": [],
                "edges": []
            }

            excluded_dirs = {
                ".git",
                "__pycache__",
                "venv",
                ".venv",
                "node_modules",
                "build",
                "dist"
            }

            python_files = []

            for root, dirs, files in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in excluded_dirs
                ]

                for file in files:

                    if file.endswith(".py"):

                        full_path = os.path.join(
                            root,
                            file
                        )

                        relative_path = os.path.relpath(
                            full_path,
                            project_path
                        ).replace("\\", "/")

                        python_files.append(
                            relative_path
                        )

            python_files = sorted(python_files)

            graph["nodes"] = python_files

            for relative_path in python_files:

                full_path = os.path.join(
                    project_path,
                    relative_path
                )

                try:
                    with open(
                        full_path,
                        "r",
                        encoding="utf-8",
                        errors="replace"
                    ) as f:
                        source = f.read()

                    tree = ast.parse(source)

                except Exception:
                    continue

                source_module = os.path.splitext(
                    relative_path
                )[0].replace("/", ".")

                for node in ast.walk(tree):

                    imported_module = None

                    if isinstance(node, ast.Import):

                        for alias in node.names:

                            imported_module = alias.name

                            for target_file in python_files:

                                target_module = os.path.splitext(
                                    target_file
                                )[0].replace("/", ".")

                                if (
                                    imported_module == target_module
                                    or imported_module.startswith(
                                        target_module + "."
                                    )
                                ):
                                    graph["edges"].append({
                                        "from": relative_path,
                                        "to": target_file
                                    })

                    elif isinstance(node, ast.ImportFrom):

                        if node.module:

                            imported_module = node.module

                            for target_file in python_files:

                                target_module = os.path.splitext(
                                    target_file
                                )[0].replace("/", ".")

                                if (
                                    imported_module == target_module
                                    or imported_module.startswith(
                                        target_module + "."
                                    )
                                ):
                                    graph["edges"].append({
                                        "from": relative_path,
                                        "to": target_file
                                    })

            unique_edges = []

            seen_edges = set()

            for edge in graph["edges"]:

                edge_key = (
                    edge["from"],
                    edge["to"]
                )

                if edge_key not in seen_edges:

                    seen_edges.add(edge_key)
                    unique_edges.append(edge)

            graph["edges"] = unique_edges

            return {
                "reply": (
                    "Architecture graph completed successfully.\n\n"
                    f"Modules/files: {len(graph['nodes'])}\n"
                    f"Internal relationships: {len(graph['edges'])}"
                ),
                "type": "coding",
                "architecture_graph": graph
            }

        except Exception as e:

            return {
                "reply": f"Architecture graph failed: {e}",
                "type": "coding"
            }

    # Code quality checking
    if (
        text.startswith("code quality ")
        or text.startswith("check code quality ")
        or text.startswith("quality check ")
    ):
        try:
            import ast

            filename = command.split(" ", 2)[-1].strip()

            if text.startswith("check code quality "):
                filename = command[len("check code quality "):].strip()
            elif text.startswith("quality check "):
                filename = command[len("quality check "):].strip()
            elif text.startswith("code quality "):
                filename = command[len("code quality "):].strip()

            if not filename:
                return {
                    "reply": "Please specify a Python file.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "File must be inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Code quality checking supports Python files only.",
                    "type": "coding"
                }

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:
                source_code = file.read()

            tree = ast.parse(
                source_code,
                filename=filename
            )

            issues = []

            for node in ast.walk(tree):

                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        issues.append({
                            "severity": "medium",
                            "issue": "Bare except detected.",
                            "line": node.lineno
                        })

                if isinstance(node, ast.Pass):
                    issues.append({
                        "severity": "low",
                        "issue": "pass statement detected.",
                        "line": node.lineno
                    })

            lines = source_code.splitlines()

            for number, line in enumerate(lines, start=1):

                if "TODO" in line or "FIXME" in line:
                    issues.append({
                        "severity": "low",
                        "issue": "TODO/FIXME comment detected.",
                        "line": number
                    })

            return {
                "reply": (
                    f"Code quality check completed for {filename}.\n\n"
                    f"Issues found: {len(issues)}"
                ),
                "type": "coding",
                "code_quality": {
                    "file": filename,
                    "issues_found": len(issues),
                    "issues": issues
                }
            }

        except SyntaxError as e:
            return {
                "reply": (
                    f"Code quality check found a syntax error "
                    f"at line {e.lineno}: {e.msg}"
                ),
                "type": "coding",
                "code_quality": {
                    "issues_found": 1,
                    "syntax_error": True
                }
            }

        except UnicodeDecodeError:
            return {
                "reply": (
                    f"Could not read {filename}: "
                    "the file is not valid UTF-8."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Code quality check failed: {e}",
                "type": "coding"
            }

    # Build a Python symbol index

    if (
        text == "index symbols"
        or text == "build symbol index"
        or text.startswith("find symbol ")
        or text.startswith("find function ")
        or text.startswith("find class ")
    ):
        try:
            import ast

            project_path = os.path.abspath(os.getcwd())
            symbols = []

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules",
                        "build",
                        "dist"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    relative_path = os.path.relpath(
                        file_path,
                        project_path
                    )

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8"
                        ) as file:
                            source_code = file.read()

                        tree = ast.parse(
                            source_code,
                            filename=relative_path
                        )

                    except (
                        OSError,
                        SyntaxError,
                        UnicodeDecodeError
                    ):
                        continue

                    for node in ast.walk(tree):

                        if isinstance(node, ast.ClassDef):

                            symbols.append({
                                "name": node.name,
                                "type": "class",
                                "file": relative_path,
                                "line": node.lineno
                            })

                        elif isinstance(
                            node,
                            (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):

                            symbols.append({
                                "name": node.name,
                                "type": "function",
                                "file": relative_path,
                                "line": node.lineno
                            })

            # Direct symbol search
            if text.startswith("find symbol "):
                search_name = command[
                    len("find symbol "):
                ].strip().lower()

                symbols = [
                    symbol
                    for symbol in symbols
                    if symbol["name"].lower() == search_name
                ]

            elif text.startswith("find function "):
                search_name = command[
                    len("find function "):
                ].strip().lower()

                symbols = [
                    symbol
                    for symbol in symbols
                    if (
                        symbol["type"] == "function"
                        and symbol["name"].lower() == search_name
                    )
                ]

            elif text.startswith("find class "):
                search_name = command[
                    len("find class "):
                ].strip().lower()

                symbols = [
                    symbol
                    for symbol in symbols
                    if (
                        symbol["type"] == "class"
                        and symbol["name"].lower() == search_name
                    )
                ]

            if not symbols:

                if (
                    text.startswith("find symbol ")
                    or text.startswith("find function ")
                    or text.startswith("find class ")
                ):
                    return {
                        "reply": "No matching symbol was found.",
                        "type": "coding",
                        "symbols": []
                    }

            return {
                "reply": (
                    f"Symbol index completed successfully.\n\n"
                    f"Symbols found: {len(symbols)}"
                ),
                "type": "coding",
                "symbols": symbols
            }

        except Exception as e:
            return {
                "reply": f"Symbol indexing failed: {e}",
                "type": "coding"
            }

    # Build a Python codebase index
    if (
        text == "index codebase"
        or text == "index project"
        or text.startswith("index codebase ")
        or text.startswith("index project ")
    ):
        try:
            import ast

            project_path = os.path.abspath(os.getcwd())
            index = {
                "files": {},
                "total_files": 0,
                "total_functions": 0,
                "total_classes": 0,
                "total_imports": 0
            }

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules",
                        "build",
                        "dist"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    relative_path = os.path.relpath(
                        file_path,
                        project_path
                    )

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8"
                        ) as file:
                            source_code = file.read()

                        tree = ast.parse(
                            source_code,
                            filename=relative_path
                        )

                    except (OSError, SyntaxError, UnicodeDecodeError):
                        continue

                    file_info = {
                        "functions": [],
                        "classes": [],
                        "imports": []
                    }

                    for node in ast.walk(tree):

                        if isinstance(
                            node,
                            (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            file_info["functions"].append({
                                "name": node.name,
                                "line": node.lineno
                            })

                            index["total_functions"] += 1

                        elif isinstance(node, ast.ClassDef):

                            file_info["classes"].append({
                                "name": node.name,
                                "line": node.lineno
                            })

                            index["total_classes"] += 1

                        elif isinstance(node, ast.Import):

                            for alias in node.names:
                                file_info["imports"].append(
                                    alias.name
                                )
                                index["total_imports"] += 1

                        elif isinstance(node, ast.ImportFrom):

                            module = node.module or ""

                            for alias in node.names:
                                if module:
                                    import_name = (
                                        f"{module}.{alias.name}"
                                    )
                                else:
                                    import_name = alias.name

                                file_info["imports"].append(
                                    import_name
                                )

                                index["total_imports"] += 1

                    index["files"][relative_path] = file_info
                    index["total_files"] += 1

            return {
                "reply": (
                    "Codebase indexing completed successfully.\n\n"
                    f"Python files: {index['total_files']}\n"
                    f"Functions: {index['total_functions']}\n"
                    f"Classes: {index['total_classes']}\n"
                    f"Imports: {index['total_imports']}"
                ),
                "type": "coding",
                "index": index
            }

        except Exception as e:
            return {
                "reply": f"Codebase indexing failed: {e}",
                "type": "coding"
            }

    # Static analysis of Python code
    if (
        text.startswith("analyze code ")
        or text.startswith("static analyze ")
        or text.startswith("analyze file ")
    ):
        try:
            if text.startswith("static analyze "):
                filename = command[len("static analyze "):].strip()
            elif text.startswith("analyze code "):
                filename = command[len("analyze code "):].strip()
            else:
                filename = command[len("analyze file "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the Python file to analyze.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only analyze files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Static analysis currently supports Python files only.",
                    "type": "coding"
                }

            import ast

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:
                source_code = file.read()

            try:
                tree = ast.parse(
                    source_code,
                    filename=filename
                )
            except SyntaxError as syntax_error:
                return {
                    "reply": (
                        f"Static analysis could not parse {filename}.\n"
                        f"Syntax error at line {syntax_error.lineno}: "
                        f"{syntax_error.msg}"
                    ),
                    "type": "coding"
                }

            issues = []

            # Detect unused imports approximately
            imported_names = []

            for node in ast.walk(tree):

                if isinstance(node, ast.Import):

                    for alias in node.names:
                        imported_names.append(
                            (
                                alias.asname
                                or alias.name.split(".")[0],
                                node.lineno
                            )
                        )

                elif isinstance(node, ast.ImportFrom):

                    for alias in node.names:

                        if alias.name == "*":
                            continue

                        imported_names.append(
                            (
                                alias.asname or alias.name,
                                node.lineno
                            )
                        )

            source_without_imports = "\n".join(
                line
                for line in source_code.splitlines()
                if not line.lstrip().startswith(
                    ("import ", "from ")
                )
            )

            for name, line_number in imported_names:

                try:
                    name_pattern = ast.Name(
                        id=name,
                        ctx=ast.Load()
                    )

                    used = any(
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id == name
                        for node in ast.walk(tree)
                    )

                    if not used:
                        issues.append(
                            f"Line {line_number}: possibly unused import '{name}'."
                        )

                except Exception:
                    continue

            # Detect pass statements
            for node in ast.walk(tree):

                if isinstance(node, ast.Pass):
                    issues.append(
                        f"Line {node.lineno}: 'pass' statement found."
                    )

            # Detect bare except
            for node in ast.walk(tree):

                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        issues.append(
                            f"Line {node.lineno}: bare 'except' catches every exception."
                        )

            # Detect TODO/FIXME markers
            for line_number, line in enumerate(
                source_code.splitlines(),
                start=1
            ):
                upper_line = line.upper()

                if "TODO" in upper_line or "FIXME" in upper_line:
                    issues.append(
                        f"Line {line_number}: TODO/FIXME marker found."
                    )

            # Ask Ollama for deeper analysis
            analysis_prompt = (
                "You are Jarvis Coding Manager.\n\n"
                "Perform a static code-quality review of this Python file.\n"
                "Do not execute it.\n"
                "Do not modify it.\n"
                "Focus on correctness risks, maintainability, complexity, "
                "possible bugs, and suspicious patterns.\n"
                "Keep the response concise.\n\n"
                f"File: {filename}\n\n"
                f"Code:\n{source_code}"
            )

            ai_analysis = ask(analysis_prompt)

            if issues:
                issue_text = "\n".join(
                    f"- {issue}"
                    for issue in issues[:50]
                )
            else:
                issue_text = "No basic static-analysis issues detected."

            return {
                "reply": (
                    f"Static analysis completed for {filename}.\n\n"
                    f"Basic findings:\n{issue_text}\n\n"
                    f"AI analysis:\n{ai_analysis}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Static analysis failed: {e}",
                "type": "coding"
            }

    # Optimize project code safely
    if (
        text.startswith("optimize ")
        or text.startswith("optimize code in ")
        or text.startswith("improve performance of ")
    ):
        try:
            if text.startswith("optimize code in "):
                request = command[len("optimize code in "):].strip()
            elif text.startswith("improve performance of "):
                request = command[len("improve performance of "):].strip()
            else:
                request = command[len("optimize "):].strip()

            if not request:
                return {
                    "reply": "Please specify the Python file and optimization request.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            target_file = None

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    relative_path = os.path.relpath(
                        os.path.join(root, filename),
                        project_path
                    )

                    if relative_path.lower() in request.lower():
                        target_file = os.path.join(
                            project_path,
                            relative_path
                        )
                        break

                if target_file:
                    break

            if not target_file:
                return {
                    "reply": (
                        "I couldn't identify the Python file to optimize. "
                        "Please include its path."
                    ),
                    "type": "coding"
                }

            filename = os.path.relpath(
                target_file,
                project_path
            )

            with open(
                target_file,
                "r",
                encoding="utf-8"
            ) as file:
                original_code = file.read()

            optimized_code = ask(
                "You are Jarvis Coding Manager performing a safe "
                "performance optimization.\n\n"
                "Optimize the Python file according to the user's request.\n"
                "Preserve existing behavior and public interfaces.\n"
                "Do not remove functionality.\n"
                "Avoid unnecessary complexity.\n"
                "Only make optimizations that are reasonably justified.\n"
                "Return ONLY the complete optimized Python file.\n"
                "Do not use Markdown code fences.\n"
                "Do not explain anything.\n\n"
                f"File: {filename}\n\n"
                f"Original code:\n{original_code}\n\n"
                f"Optimization request:\n{request}"
            )

            if not optimized_code or not optimized_code.strip():
                return {
                    "reply": "The coding model returned no optimized code.",
                    "type": "coding"
                }

            optimized_code = optimized_code.strip()

            if optimized_code.startswith("```"):
                lines = optimized_code.splitlines()

                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                optimized_code = "\n".join(lines).strip()

            backup_path = target_file + ".jarvis_backup"

            with open(
                backup_path,
                "w",
                encoding="utf-8"
            ) as backup:
                backup.write(original_code)

            with open(
                target_file,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(optimized_code)

            import py_compile

            try:
                py_compile.compile(
                    target_file,
                    doraise=True
                )

            except Exception as verification_error:

                with open(
                    target_file,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(original_code)

                return {
                    "reply": (
                        f"Optimization failed verification for {filename}.\n"
                        "Original file restored.\n\n"
                        f"Error: {verification_error}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully optimized and verified {filename}.\n"
                    f"Backup created: {os.path.basename(backup_path)}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Code optimization failed: {e}",
                "type": "coding"
            }

    # Refactor project code safely
    if (
        text.startswith("refactor ")
        or text.startswith("refactor code in ")
        or text.startswith("clean up code in ")
    ):
        try:
            if text.startswith("refactor code in "):
                request = command[len("refactor code in "):].strip()
            elif text.startswith("clean up code in "):
                request = command[len("clean up code in "):].strip()
            else:
                request = command[len("refactor "):].strip()

            if not request:
                return {
                    "reply": "Please specify the file and refactoring you want.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            target_file = None

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    relative_path = os.path.relpath(
                        os.path.join(root, filename),
                        project_path
                    )

                    if relative_path.lower() in request.lower():
                        target_file = os.path.join(
                            project_path,
                            relative_path
                        )
                        break

                if target_file:
                    break

            if not target_file:
                return {
                    "reply": (
                        "I couldn't identify the Python file to refactor. "
                        "Please include its path."
                    ),
                    "type": "coding"
                }

            filename = os.path.relpath(
                target_file,
                project_path
            )

            with open(
                target_file,
                "r",
                encoding="utf-8"
            ) as file:
                original_code = file.read()

            refactored_code = ask(
                "You are Jarvis Coding Manager performing a safe refactor.\n\n"
                "Refactor the Python file according to the user's request.\n"
                "Preserve the existing behavior unless the user explicitly "
                "requests a behavior change.\n"
                "Improve readability, structure, maintainability, and "
                "remove unnecessary duplication where appropriate.\n"
                "Return ONLY the complete refactored Python file.\n"
                "Do not use Markdown code fences.\n"
                "Do not explain anything.\n\n"
                f"File: {filename}\n\n"
                f"Original code:\n{original_code}\n\n"
                f"Refactoring request:\n{request}"
            )

            if not refactored_code or not refactored_code.strip():
                return {
                    "reply": "The coding model returned no refactored code.",
                    "type": "coding"
                }

            refactored_code = refactored_code.strip()

            if refactored_code.startswith("```"):
                lines = refactored_code.splitlines()

                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                refactored_code = "\n".join(lines).strip()

            backup_path = target_file + ".jarvis_backup"

            with open(
                backup_path,
                "w",
                encoding="utf-8"
            ) as backup:
                backup.write(original_code)

            with open(
                target_file,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(refactored_code)

            import py_compile

            try:
                py_compile.compile(
                    target_file,
                    doraise=True
                )

            except Exception as verification_error:

                with open(
                    target_file,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(original_code)

                return {
                    "reply": (
                        f"Refactor failed verification for {filename}.\n"
                        "Original file restored.\n\n"
                        f"Error: {verification_error}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully refactored and verified {filename}.\n"
                    f"Backup created: {os.path.basename(backup_path)}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Refactoring failed: {e}",
                "type": "coding"
            }

    # Root cause analysis
    if (
        text.startswith("analyze root cause ")
        or text.startswith("find root cause ")
        or text.startswith("root cause analysis ")
        or text.startswith("why is this code failing ")
    ):
        try:
            if text.startswith("analyze root cause "):
                problem = command[len("analyze root cause "):].strip()

            elif text.startswith("find root cause "):
                problem = command[len("find root cause "):].strip()

            elif text.startswith("root cause analysis "):
                problem = command[len("root cause analysis "):].strip()

            else:
                problem = command[len("why is this code failing "):].strip()

            if not problem:
                return {
                    "reply": "Please provide the error, code, or problem to analyze.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, problem)
            )

            # If the argument is a project file, read its contents.
            if (
                os.path.isfile(file_path)
                and os.path.commonpath(
                    [project_path, file_path]
                ) == project_path
            ):
                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                    errors="replace"
                ) as f:
                    problem_content = f.read()

                problem = (
                    f"File: {problem}\n\n"
                    f"File contents:\n{problem_content}"
                )

            reply = ask(
                "You are Jarvis Coding Manager performing root-cause analysis.\n\n"
                "Analyze the coding problem below.\n\n"
                "Determine:\n"
                "1. The immediate problem.\n"
                "2. The underlying root cause.\n"
                "3. Why the problem happened.\n"
                "4. Which project component may be affected.\n"
                "5. Possible secondary effects.\n"
                "6. The safest recommended fix.\n"
                "7. Whether other files should be inspected before changing anything.\n\n"
                "Do NOT modify files.\n"
                "Do NOT claim that a file is affected unless the provided information supports it.\n\n"
                f"Project path: {project_path}\n\n"
                f"Problem:\n{problem}"
            )

            return {
                "reply": reply,
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Root-cause analysis failed: {e}",
                "type": "coding"
            }
    # Analyze Python traceback
    if (
        text.startswith("analyze traceback ")
        or text.startswith("explain traceback ")
        or text.startswith("analyze this traceback ")
        or text.startswith("analyze this error ")
    ):
        try:
            if text.startswith("analyze traceback "):
                traceback_text = command[len("analyze traceback "):].strip()

            elif text.startswith("explain traceback "):
                traceback_text = command[len("explain traceback "):].strip()

            elif text.startswith("analyze this traceback "):
                traceback_text = command[len("analyze this traceback "):].strip()

            else:
                traceback_text = command[len("analyze this error "):].strip()

            if not traceback_text:
                return {
                    "reply": "Please provide the traceback or error.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, traceback_text)
            )

            # If the argument is a project file, read its contents.
            if (
                os.path.isfile(file_path)
                and os.path.commonpath(
                    [project_path, file_path]
                ) == project_path
            ):
                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                    errors="replace"
                ) as f:
                    traceback_text = f.read()
    # Root
            reply = ask(
                "You are Jarvis Coding Manager.\n\n"
                "Analyze this Python error or traceback.\n\n"
                "Explain:\n"
                "1. Error type\n"
                "2. File and line if available\n"
                "3. What went wrong\n"
                "4. Likely cause\n"
                "5. Clear suggested fix\n\n"
                "Do not modify any files.\n\n"
                f"Traceback/Error:\n{traceback_text}"
            )

            return {
                "reply": reply,
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Traceback analysis failed: {e}",
                "type": "coding"
            }

    # Generate tests for project code
    if (
        text.startswith("write tests for ")
        or text.startswith("create tests for ")
        or text.startswith("generate tests for ")
        or text.startswith("write test for ")
    ):
        try:
            if text.startswith("write tests for "):
                filename = command[len("write tests for "):].strip()
            elif text.startswith("create tests for "):
                filename = command[len("create tests for "):].strip()
            elif text.startswith("generate tests for "):
                filename = command[len("generate tests for "):].strip()
            else:
                filename = command[len("write test for "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the file to test.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only create tests inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:
                source_code = file.read()

            test_code = ask(
                "You are Jarvis Coding Manager.\n\n"
                "Generate useful pytest tests for the Python file below.\n"
                "Return ONLY valid Python test code.\n"
                "Do not use Markdown code fences.\n"
                "Do not modify the source file.\n\n"
                f"Source file: {filename}\n\n"
                f"Source code:\n{source_code}"
            )

            if not test_code or not test_code.strip():
                return {
                    "reply": "The coding model did not generate any tests.",
                    "type": "coding"
                }

            test_code = test_code.strip()

            if test_code.startswith("```"):
                lines = test_code.splitlines()

                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                test_code = "\n".join(lines).strip()

            test_dir = os.path.join(project_path, "tests")
            os.makedirs(test_dir, exist_ok=True)

            base_name = os.path.splitext(
                os.path.basename(filename)
            )[0]

            test_filename = f"test_{base_name}.py"
            test_path = os.path.join(test_dir, test_filename)

            if os.path.exists(test_path):
                return {
                    "reply": (
                        f"Test file already exists: "
                        f"tests/{test_filename}"
                    ),
                    "type": "coding"
                }

            with open(
                test_path,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(test_code)

            import py_compile

            try:
                py_compile.compile(
                    test_path,
                    doraise=True
                )

            except Exception as verification_error:
                os.remove(test_path)

                return {
                    "reply": (
                        "Generated test failed syntax verification.\n"
                        "The invalid test file was removed.\n\n"
                        f"Error: {verification_error}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully generated and verified tests for "
                    f"{filename}.\n"
                    f"Test file: tests/{test_filename}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Test generation failed: {e}",
                "type": "coding"
            }

    # Create a new project folder
    if (
        text.startswith("create folder ")
        or text.startswith("create a folder ")
        or text.startswith("make folder ")
        or text.startswith("make a folder ")
        or text.startswith("create directory ")
    ):
        try:
            if text.startswith("create a folder "):
                foldername = command[len("create a folder "):].strip()
            elif text.startswith("create folder "):
                foldername = command[len("create folder "):].strip()
            elif text.startswith("make a folder "):
                foldername = command[len("make a folder "):].strip()
            elif text.startswith("make folder "):
                foldername = command[len("make folder "):].strip()
            else:
                foldername = command[len("create directory "):].strip()

            if not foldername:
                return {
                    "reply": "Please specify the folder name.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            folder_path = os.path.abspath(
                os.path.join(project_path, foldername)
            )

            # Security: keep creation inside the Jarvis project
            if os.path.commonpath(
                [project_path, folder_path]
            ) != project_path:
                return {
                    "reply": "I can only create folders inside the Jarvis project.",
                    "type": "coding"
                }

            if os.path.exists(folder_path):
                return {
                    "reply": f"Folder already exists: {foldername}",
                    "type": "coding"
                }

            os.makedirs(folder_path)

            return {
                "reply": f"Successfully created folder: {foldername}",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Folder creation failed: {e}",
                "type": "coding"
            }

    # Create a new project file
    if (
        text.startswith("create file ")
        or text.startswith("create a file ")
        or text.startswith("make file ")
        or text.startswith("make a file ")
    ):
        try:
            if text.startswith("create a file "):
                filename = command[len("create a file "):].strip()
            elif text.startswith("create file "):
                filename = command[len("create file "):].strip()
            elif text.startswith("make a file "):
                filename = command[len("make a file "):].strip()
            else:
                filename = command[len("make file "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the file name.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            # Security: keep creation inside the Jarvis project
            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only create files inside the Jarvis project.",
                    "type": "coding"
                }

            if os.path.exists(file_path):
                return {
                    "reply": f"File already exists: {filename}",
                    "type": "coding"
                }

            parent = os.path.dirname(file_path)

            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as file:
                file.write("")

            return {
                "reply": f"Successfully created file: {filename}",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"File creation failed: {e}",
                "type": "coding"
            }

    # Format Python code
    if (
        text.startswith("format code ")
        or text.startswith("format file ")
    ):
        try:
            if text.startswith("format code "):
                filename = command[len("format code "):].strip()
            else:
                filename = command[len("format file "):].strip()

            if not filename:
                return {
                    "reply": "Please specify a Python file to format.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": (
                        "I can only format files inside "
                        "the Jarvis project."
                    ),
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "Code formatting currently supports Python files only.",
                    "type": "coding"
                }

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "format",
                    file_path
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode != 0:
                output = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "Ruff formatting failed."
                )

                return {
                    "reply": (
                        f"Code formatting failed for {filename}.\n\n"
                        f"{output}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully formatted {filename} "
                    "with Ruff."
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Code formatting failed: {e}",
                "type": "coding"
            }

    # Explain code
    if (
        text.startswith("explain")
        and not text.startswith("explain file ")
    ):
        reply = ask(
            "Explain the following coding question clearly and simply. "
            "If the user asks about a programming language, explain its "
            "purpose, basic syntax, and a small example.\n\n"
            f"User request: {command}"
        )

        return {
            "reply": reply,
            "type": "coding"
        }

    # Create/write code
    if (
        text.startswith("write code")
        or text.startswith("create code")
        or text.startswith("write python")
        or text.startswith("create python")
        or "write a program" in text
        or "create a program" in text
    ):
        reply = ask(
            "Write the code requested by the user. "
            "Return clean, working code and briefly explain what it does. "
            "If no programming language is specified, use Python.\n\n"
            f"User request: {command}"
        )

        return {
            "reply": reply,
            "type": "coding"
        }

    # Debug code
    if (
        "debug" in text
        or "fix this code" in text
        or "fix the error" in text
    ):
        reply = ask(
            "Act as a Python/code debugging expert. "
            "Analyze the user's code or error, identify the problem, "
            "explain the cause simply, and provide corrected code.\n\n"
            f"User request: {command}"
        )

        return {
            "reply": reply,
            "type": "coding"
        }

    # Run/Test Python code
    if (
        text.startswith("run python")
        or text.startswith("test python")
        or "run this code" in text
        or "test this code" in text
    ):
        code = command

        if code.lower().startswith("run python"):
            code = code[10:].strip()

        elif code.lower().startswith("test python"):
            code = code[11:].strip()

        if not code:
            return {
                "reply": "Please provide the Python code to run.",
                "type": "coding"
            }

        try:
            import subprocess

            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                output = result.stdout.strip()

                return {
                    "reply": f"Code executed successfully.\nOutput: {output}",
                    "type": "coding"
                }

            error = result.stderr.strip()

            return {
                "reply": f"Code failed.\nError: {error}",
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": "Code stopped because it took too long to finish.",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Execution error: {e}",
                "type": "coding"
            }

    # Semantic code search
    if (
        text.startswith("semantic search ")
        or text.startswith("search code by meaning ")
        or text.startswith("find code by meaning ")
    ):
        try:
            query = command.split(" ", 2)[-1].strip()

            if not query:
                return {
                    "reply": "Please specify what you want to search for.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            candidates = []

            # Extract meaningful search terms.
            import re

            stop_words = {
                "the",
                "a",
                "an",
                "for",
                "of",
                "in",
                "to",
                "that",
                "code",
                "file",
                "files",
                "function",
                "class",
                "handles",
                "handling"
            }

            query_words = {
                word.lower()
                for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
                if word.lower() not in stop_words
            }

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules",
                        "build",
                        "dist"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    relative_path = os.path.relpath(
                        file_path,
                        project_path
                    )

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8",
                            errors="replace"
                        ) as file:
                            content = file.read()

                    except OSError:
                        continue

                    if not content.strip():
                        continue

                    content_lower = content.lower()
                    filename_lower = filename.lower()

                    # Score files using semantic hints plus
                    # meaningful keyword overlap.
                    score = 0

                    for word in query_words:
                        if word in filename_lower:
                            score += 5

                        score += content_lower.count(word)

                    # Give additional weight to likely semantic matches.
                    semantic_groups = {
                        "virtual": {
                            "venv",
                            "virtualenv",
                            "virtual",
                            "environment",
                            "conda"
                        },
                        "environment": {
                            "venv",
                            "virtualenv",
                            "virtual",
                            "environment",
                            "conda",
                            "os.environ"
                        },
                        "test": {
                            "pytest",
                            "unittest",
                            "test",
                            "assert"
                        },
                        "database": {
                            "sqlite",
                            "database",
                            "sql",
                            "cursor"
                        },
                        "network": {
                            "http",
                            "request",
                            "socket",
                            "api",
                            "url"
                        }
                    }

                    query_lower = query.lower()

                    for group_name, related_terms in semantic_groups.items():
                        if group_name in query_lower:
                            for term in related_terms:
                                if term in content_lower:
                                    score += 3

                    if score > 0:
                        candidates.append(
                            {
                                "file": relative_path,
                                "content": content,
                                "score": score
                            }
                        )

            if not candidates:
                return {
                    "reply": (
                        "No semantically relevant Python code "
                        "was found for that search."
                    ),
                    "type": "coding",
                    "query": query,
                    "files_searched": 0,
                    "results": []
                }

            # Highest-scoring files first.
            candidates.sort(
                key=lambda item: item["score"],
                reverse=True
            )

            # Send only the strongest candidates to Ollama.
            top_candidates = candidates[:15]

            candidate_text = "\n\n---\n\n".join(
                (
                    f"FILE: {item['file']}\n"
                    f"RELEVANCE SCORE: {item['score']}\n"
                    f"CODE:\n{item['content'][:5000]}"
                )
                for item in top_candidates
            )

            reply = (
                f"Semantic search completed.\n\n"
                f"Query: {query}\n\n"
                "Most relevant files:\n"
                + "\n".join(
                    f"{index}. {item['file']} "
                    f"(relevance score: {item['score']})"
                    for index, item in enumerate(
                        top_candidates[:10],
                        start=1
                    )
                )
            )


            if not reply or not reply.strip():
                reply = (
                    "Semantic search completed. "
                    "The highest-ranked matching files are:\n\n"
                    + "\n".join(
                        f"- {item['file']} "
                        f"(score: {item['score']})"
                        for item in top_candidates[:5]
                    )
                )


            return {
                "reply": reply,
                "type": "coding",
                "query": query,
                "files_searched": len(code_files) if "code_files" in locals() else len(candidates),
                "results": [
                    {
                        "file": item["file"],
                        "score": item["score"]
                    }
                    for item in top_candidates
                ]
            }

        except Exception as e:
            return {
                "reply": f"Semantic code search failed: {e}",
                "type": "coding"
            }


    # Analyze project
    if (
        "analyze my project" in text
        or "analyze this project" in text
        or "analyze project" in text
        or "explain my project" in text
    ):
        try:
            project_path = os.getcwd()

            files = []

            for root, dirs, filenames in os.walk(project_path):

                # Ignore unnecessary folders
                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules"
                    }
                ]

                for filename in filenames:

                    files.append(
                        os.path.relpath(
                            os.path.join(root, filename),
                            project_path
                        )
                    )

            if not files:
                return {
                    "reply": "No project files found.",
                    "type": "coding"
                }

            file_list = "\n".join(files[:200])

            reply = ask(
                "Analyze this project structure and explain "
                "what the project appears to do. "
                "Identify important folders and files. "
                "Do not modify anything.\n\n"
                f"Project files:\n{file_list}"
            )

            return {
                "reply": reply,
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Project analysis failed: {e}",
                "type": "coding"
            }

    # Read project file
    if (
        text.startswith("read ")
        or text.startswith("explain file ")
        or text.startswith("show file ")
    ):
        try:
            if text.startswith("explain file "):
                filename = command[13:].strip()
            elif text.startswith("show file "):
                filename = command[10:].strip()
            else:
                filename = command[5:].strip()

            if not filename:
                return {
                    "reply": "Please specify a file name.",
                    "type": "coding"
                }

            project_path = os.getcwd()
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            # Prevent reading files outside the Jarvis project
            if not file_path.startswith(project_path):
                return {
                    "reply": "I can only read files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as file:
                content = file.read()

            if not content.strip():
                return {
                    "reply": f"{filename} is empty.",
                    "type": "coding"
                }

            reply = ask(
                "Analyze the following project file. "
                "Explain what it does, its important functions, "
                "and any obvious problems. Do not modify the file.\n\n"
                f"FILE: {filename}\n\n"
                f"{content}"
            )

            return {
                "reply": reply,
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Could not read the file: {e}",
                "type": "coding"
            }

    # Find code/text across the project
    if (
        text.startswith("find ")
        or text.startswith("where is ")
        or text.startswith("search project for ")
        or text.startswith("search for ")
        or "find all files containing " in text
    ):
        try:
            if text.startswith("find all files containing "):
                search_term = command[
                    len("find all files containing "):
                ].strip()

            elif text.startswith("search project for "):
                search_term = command[
                    len("search project for "):
                ].strip()

            elif text.startswith("search for "):
                search_term = command[
                    len("search for "):
                ].strip()

            elif text.startswith("where is "):
                search_term = command[
                    len("where is "):
                ].strip()
            else:
                search_term = command[
                    len("find "):
                ].strip()

            if not search_term:
                return {
                    "reply": "Please specify what you want me to find.",
                    "type": "coding"
                }

            project_path = os.getcwd()
            matches = []

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules"
                    }
                ]

                for filename in filenames:

                    allowed_extensions = {
                        ".py",
                        ".txt",
                        ".json",
                        ".md",
                        ".yaml",
                        ".yml",
                        ".toml",
                        ".ini",
                        ".cfg"
                    }

                    extension = os.path.splitext(filename)[1].lower()

                    if extension not in allowed_extensions:
                        continue

                    file_path = os.path.join(root, filename)

                    try:
                        with open(
                            file_path,
                            "r",
                            encoding="utf-8",
                            errors="ignore"
                        ) as file:

                            for line_number, line in enumerate(
                                file,
                                start=1
                            ):
                                if search_term.lower() in line.lower():

                                    relative_path = os.path.relpath(
                                        file_path,
                                        project_path
                                    )

                                    matches.append(
                                        f"{relative_path}:{line_number}: "
                                        f"{line.strip()}"
                                    )

                    except (OSError, UnicodeDecodeError):
                        continue

            if not matches:
                return {
                    "reply": (
                        f"I couldn't find '{search_term}' "
                        "in the project."
                    ),
                    "type": "coding"
                }

            # Prevent an enormous response
            matches = matches[:50]

            return {
                "reply": (
                    f"Found '{search_term}' in "
                    f"{len(matches)} location(s):\n\n"
                    + "\n".join(matches)
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Project search failed: {e}",
                "type": "coding"
            }

    # Check project for Python errors
    if (
        "check my project for errors" in text
        or "find errors in my project" in text
        or "check my code" in text
        or "check project errors" in text
    ):
        try:
            import subprocess

            project_path = os.getcwd()
            errors = []

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules",
                        "build",
                        "dist"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    file_path = os.path.join(root, filename)

                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "--disable-warnings",
                            "--maxfail=5"
                        ],
                        capture_output=True,
                        text=True
                    )

                    if result.returncode != 0:

                        relative_path = os.path.relpath(
                            file_path,
                            project_path
                        )

                        errors.append(
                            f"{relative_path}\n"
                            f"{result.stderr.strip()}"
                        )

            if not errors:
                return {
                    "reply": "Project check complete. No Python syntax errors were found.",
                    "type": "coding"
                }

            error_text = "\n\n".join(errors)

            analysis = ask(
                "You are Jarvis Coding Manager.\n\n"
                "Analyze these Python project errors.\n"
                "For each error:\n"
                "1. Identify the file.\n"
                "2. Explain what went wrong.\n"
                "3. Explain the likely cause.\n"
                "4. Give a clear suggested fix.\n"
                "Do NOT modify any files.\n\n"
                f"Detected errors:\n{error_text}"
            )

            return {
                "reply": (
                    f"Found {len(errors)} Python file(s) "
                    "with syntax errors.\n\n"
                    + analysis
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Project error scan failed: {e}",
                "type": "coding"
            }

        # Modify project code safely
    if (
        text.startswith("modify ")
        or text.startswith("change code in ")
        or text.startswith("edit code in ")
    ):
        try:
            # Extract request
            if text.startswith("modify "):
                request = command[7:].strip()
            elif text.startswith("change code in "):
                request = command[len("change code in "):].strip()
            else:
                request = command[len("edit code in "):].strip()

            if not request:
                return {
                    "reply": "Please specify what you want me to modify.",
                    "type": "coding"
                }

            # Find the target Python file mentioned in the request
            project_path = os.path.abspath(os.getcwd())
            target_file = None

            for root, dirs, filenames in os.walk(project_path):

                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "node_modules"
                    }
                ]

                for filename in filenames:

                    if not filename.endswith(".py"):
                        continue

                    relative_path = os.path.relpath(
                        os.path.join(root, filename),
                        project_path
                    )

                    if relative_path.lower() in request.lower():
                        target_file = os.path.join(
                            project_path,
                            relative_path
                        )
                        break

                if target_file:
                    break

            if not target_file:
                return {
                    "reply": (
                        "I couldn't identify the Python file to modify. "
                        "Please include its path, for example: "
                        "modify brains_v2/intent.py ..."
                    ),
                    "type": "coding"
                }

            filename = os.path.relpath(
                target_file,
                project_path
            )

            # Read original code
            with open(
                target_file,
                "r",
                encoding="utf-8"
            ) as file:
                original_code = file.read()

            # Ask the coding model for the complete modified file
            modified_code = ask(
                "You are Jarvis Coding Manager.\n\n"
                "Modify the Python file according to the user's request.\n"
                "Return ONLY the complete modified Python file.\n"
                "Do not use Markdown code fences.\n"
                "Do not explain anything.\n\n"
                f"File: {filename}\n\n"
                f"Original code:\n{original_code}\n\n"
                f"Modification request:\n{request}"
            )

            if not modified_code or not modified_code.strip():
                return {
                    "reply": "The coding model returned no modified code.",
                    "type": "coding"
                }

            modified_code = modified_code.strip()

            # Remove Markdown fences if the model accidentally adds them
            if modified_code.startswith("```"):
                lines = modified_code.splitlines()

                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                modified_code = "\n".join(lines).strip()

            # Create backup
            backup_path = target_file + ".jarvis_backup"

            with open(
                backup_path,
                "w",
                encoding="utf-8"
            ) as backup:
                backup.write(original_code)

            # Write modification
            with open(
                target_file,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(modified_code)

            # Verify syntax
            import py_compile

            try:
                py_compile.compile(
                    target_file,
                    doraise=True
                )

            except Exception as verification_error:

                # Roll back automatically
                with open(
                    target_file,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(original_code)

                return {
                    "reply": (
                        f"Modification failed verification for {filename}.\n"
                        "Original file restored.\n\n"
                        f"Error: {verification_error}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully modified and verified {filename}.\n"
                    f"Backup created: {os.path.basename(backup_path)}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Code modification failed: {e}",
                "type": "coding"
            }

    # Safely fix a specific Python file
    if (
        text.startswith("fix errors in ")
        or text.startswith("fix error in ")
        or text.startswith("fix ")
    ):
        try:
            # Get filename from command
            if text.startswith("fix errors in "):
                filename = command[len("fix errors in "):].strip()
            elif text.startswith("fix error in "):
                filename = command[len("fix error in "):].strip()
            else:
                filename = command[len("fix "):].strip()

            if not filename:
                return {
                    "reply": "Please specify the Python file to fix.",
                    "type": "coding"
                }

            project_path = os.path.abspath(os.getcwd())
            file_path = os.path.abspath(
                os.path.join(project_path, filename)
            )

            # Security: keep the operation inside Jarvis project
            if os.path.commonpath(
                [project_path, file_path]
            ) != project_path:
                return {
                    "reply": "I can only modify files inside the Jarvis project.",
                    "type": "coding"
                }

            if not os.path.isfile(file_path):
                return {
                    "reply": f"File not found: {filename}",
                    "type": "coding"
                }

            if not filename.lower().endswith(".py"):
                return {
                    "reply": "For now, I can only automatically fix Python files.",
                    "type": "coding"
                }

            # Read original code
            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as file:
                original_code = file.read()

            if not original_code.strip():
                return {
                    "reply": f"{filename} is empty.",
                    "type": "coding"
                }

            # Ask Ollama for corrected code
            fixed_code = ask(
                "Fix the Python code below.\n\n"
                "Return ONLY the complete corrected Python code. "
                "Do not use Markdown fences. "
                "Do not explain anything.\n\n"
                f"FILE: {filename}\n\n"
                f"{original_code}"
            )

            if not fixed_code or not fixed_code.strip():
                return {
                    "reply": "Ollama did not provide corrected code.",
                    "type": "coding"
                }

            # Remove accidental Markdown fences
            fixed_code = fixed_code.strip()

            if fixed_code.startswith("```"):
                lines = fixed_code.splitlines()

                if lines and lines[0].startswith("```"):
                    lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                fixed_code = "\n".join(lines).strip()

            # Create backup
            backup_path = file_path + ".jarvis_backup"

            with open(
                backup_path,
                "w",
                encoding="utf-8"
            ) as backup:
                backup.write(original_code)

            # Write proposed fix
            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(fixed_code)

            # Verify syntax
            import py_compile

            try:
                py_compile.compile(
                    file_path,
                    doraise=True
                )

            except Exception as verification_error:

                # Restore original code
                with open(
                    file_path,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(original_code)

                return {
                    "reply": (
                        f"Fix failed verification for {filename}.\n"
                        f"Original file restored.\n\n"
                        f"Error: {verification_error}"
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    f"Successfully fixed and verified {filename}.\n"
                    f"Backup created: {os.path.basename(backup_path)}"
                ),
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Automatic fix failed: {e}",
                "type": "coding"
            }

    # Run project tests
    if (
        "run my tests" in text
        or "test my project" in text
        or "run project tests" in text
        or "run all tests" in text
    ):
        try:
            import subprocess

            project_path = os.getcwd()

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q"
                ],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = result.stdout.strip()
            error = result.stderr.strip()

            if result.returncode == 0:
                return {
                    "reply": (
                        "Project tests completed successfully.\n\n"
                        + (output or "No test output.")
                    ),
                    "type": "coding"
                }

            return {
                "reply": (
                    "Project tests found failures.\n\n"
                    + (output or error or "Unknown test failure.")
                ),
                "type": "coding"
            }

        except FileNotFoundError:
            return {
                "reply": (
                    "Pytest is not installed in this Python environment."
                ),
                "type": "coding"
            }

        except subprocess.TimeoutExpired:
            return {
                "reply": "Project tests exceeded the 120-second limit.",
                "type": "coding"
            }

        except Exception as e:
            return {
                "reply": f"Test execution failed: {e}",
                "type": "coding"
            }

    # Build complete application
    if (
        text.startswith("build application ")
        or text.startswith("build app ")
        or text.startswith("create complete application ")
        or text.startswith("create complete app ")
    ):
        try:
            request = command.split(" ", 2)[2].strip()

            if not request:
                return {
                    "reply": "Please describe the application you want me to build.",
                    "type": "coding"
                }

            project_path = os.path.join(
                os.getcwd(),
                "generated_apps"
            )

            os.makedirs(project_path, exist_ok=True)

            plan_prompt = (
                "You are Jarvis Coding Manager.\n\n"
                "Plan a complete Python application from the user's request.\n"
                "Return ONLY valid JSON.\n"
                "Use this exact structure:\n"
                "{\n"
                '  "project_name": "name",\n'
                '  "files": [\n'
                '    {"path": "main.py", "purpose": "description"}\n'
                "  ],\n"
                '  "dependencies": []\n'
                "}\n\n"
                "Rules:\n"
                "- Use Python.\n"
                "- Keep the project reasonably small.\n"
                "- Include all files required for a runnable application.\n"
                "- Do not use Markdown fences.\n\n"
                f"Application request:\n{request}"
            )

            plan = ask(plan_prompt)

            import json

            try:
                plan_data = json.loads(plan)
            except json.JSONDecodeError:
                return {
                    "reply": (
                        "The coding AI returned an invalid project plan.\n\n"
                        f"{plan}"
                    ),
                    "type": "coding"
                }

            project_name = plan_data.get(
                "project_name",
                "generated_application"
            )

            project_name = "".join(
                c for c in project_name
                if c.isalnum() or c in "_-"
            ).strip("_-")

            if not project_name:
                project_name = "generated_application"

            app_directory = os.path.join(
                project_path,
                project_name
            )

            os.makedirs(app_directory, exist_ok=True)

            generated_files = []

            for file_info in plan_data.get("files", []):
                relative_path = file_info.get("path", "").strip()
                purpose = file_info.get("purpose", "").strip()

                if not relative_path:
                    continue

                file_path = os.path.abspath(
                    os.path.join(app_directory, relative_path)
                )

                if not file_path.startswith(
                    os.path.abspath(app_directory) + os.sep
                ):
                    continue

                os.makedirs(
                    os.path.dirname(file_path),
                    exist_ok=True
                )

                code_prompt = (
                    "You are Jarvis Coding Manager.\n\n"
                    "Generate the complete runnable Python code "
                    "for one file in a new application.\n\n"
                    "Return ONLY the code.\n"
                    "Do not use Markdown code fences.\n"
                    "Do not use placeholders.\n"
                    "Do not use TODO comments instead of implementation.\n\n"
                    f"Application request:\n{request}\n\n"
                    f"File path:\n{relative_path}\n\n"
                    f"File purpose:\n{purpose}\n\n"
                    f"Project plan:\n{plan}"
                )

                generated_code = ask(code_prompt)

                if (
                    not generated_code
                    or not generated_code.strip()
                    or generated_code.strip().lower()
                    in {
                        "empty response received from ollama.",
                        "empty response received from ollama"
                    }
                ):
                    generated_code = ask(code_prompt)

                    if (
                        not generated_code
                        or not generated_code.strip()
                        or generated_code.strip().lower()
                        in {
                            "empty response received from ollama.",
                            "empty response received from ollama"
                        }
                    ):
                        return {
                            "reply": (
                                f"AI failed to generate valid code for {relative_path}."
                            ),
                            "type": "coding"
                        }

                generated_code = generated_code.strip()

                if generated_code.startswith("```"):
                    lines = generated_code.splitlines()

                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]

                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]

                    generated_code = "\n".join(lines)

                with open(
                    file_path,
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(generated_code)

                generated_files.append(relative_path)

            dependencies = plan_data.get(
                "dependencies",
                []
            )

            # Install declared dependencies
            import subprocess
            import time

            for dependency in dependencies:
                dependency = str(dependency).strip()

                if not dependency:
                    continue

                install_result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        dependency
                    ],
                    cwd=app_directory,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120
                )

                if install_result.returncode != 0:
                    return {
                        "reply": (
                            f"Dependency installation failed: "
                            f"{dependency}\n\n"
                            f"{install_result.stderr.strip()}"
                        ),
                        "type": "coding",
                        "build_complete_application": True,
                        "build_directory": app_directory,
                        "generated_files": generated_files,
                        "dependencies": dependencies
                    }

            # Verify generated Python files
            python_files = []

            for root, _, filenames in os.walk(app_directory):
                for filename in filenames:
                    if filename.endswith(".py"):
                        python_files.append(
                            os.path.join(root, filename)
                        )

            for python_file in python_files:
                compile_result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "py_compile",
                        python_file
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )

                if compile_result.returncode != 0:
                    return {
                        "reply": (
                            "Application build failed syntax verification.\n\n"
                            f"File: {python_file}\n\n"
                            f"{compile_result.stderr.strip()}"
                        ),
                        "type": "coding",
                        "build_complete_application": True,
                        "build_directory": app_directory,
                        "generated_files": generated_files,
                        "dependencies": dependencies
                    }

            # Determine application entry point
            entry_point = None

            if os.path.exists(
                os.path.join(app_directory, "main.py")
            ):
                entry_point = "main.py"

            elif python_files:
                entry_point = os.path.relpath(
                    python_files[0],
                    app_directory
                )

            if not entry_point:
                return {
                    "reply": (
                        "Application files were generated, but "
                        "no Python entry point was found."
                    ),
                    "type": "coding"
                }

            # Automatic runtime error detection and AI repair
            max_fix_attempts = 3
            last_runtime_error = None

            for attempt in range(1, max_fix_attempts + 1):

                process_handle = subprocess.Popen(
                    [
                        sys.executable,
                        entry_point
                    ],
                    cwd=app_directory,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )

                time.sleep(3)

                # Application is still running
                if process_handle.poll() is None:
                    return {
                        "reply": (
                            "Complete application built successfully.\n\n"
                            f"Project: {project_name}\n"
                            f"Location: {app_directory}\n"
                            f"Entry point: {entry_point}\n\n"
                            "Generated files:\n"
                            + (
                                "\n".join(
                                    f"- {file}"
                                    for file in generated_files
                                )
                                or "- No files generated"
                            )
                            + "\n\nApplication passed syntax "
                            "and runtime verification."
                        ),
                        "type": "coding",
                        "build_complete_application": True,
                        "build_directory": app_directory,
                        "generated_files": generated_files,
                        "dependencies": dependencies,
                        "runtime_verified": True,
                        "process_id": process_handle.pid,
                        "fix_attempts": attempt - 1
                    }

                # Application crashed
                stdout, stderr = process_handle.communicate(
                    timeout=10
                )

                runtime_error = (
                    stderr.strip()
                    or stdout.strip()
                    or f"Application exited with code {process_handle.returncode}."
                )

                last_runtime_error = runtime_error

                if attempt >= max_fix_attempts:
                    break

                # Read the entry-point source
                try:
                    with open(
                        os.path.join(app_directory, entry_point),
                        "r",
                        encoding="utf-8",
                        errors="replace"
                    ) as file:
                        current_code = file.read()

                except Exception as read_error:
                    return {
                        "reply": (
                            "Application crashed, but the source file "
                            f"could not be read.\n\n{read_error}\n\n"
                            f"Runtime error:\n{runtime_error}"
                        ),
                        "type": "coding",
                        "build_complete_application": True,
                        "build_directory": app_directory,
                        "generated_files": generated_files,
                        "runtime_verified": False,
                        "runtime_error": runtime_error
                    }

                # Ask the coding AI to repair the application
                fixed_code = ask(
                    "You are Jarvis Coding Manager repairing a generated "
                    "Python application.\n\n"
                    "The application crashed during runtime verification.\n"
                    "Analyze the error and fix the source code.\n\n"
                    "Rules:\n"
                    "- Return ONLY the complete corrected Python file.\n"
                    "- Do not use Markdown code fences.\n"
                    "- Preserve the application's intended functionality.\n"
                    "- Do not remove functionality just to hide the error.\n"
                    "- Do not use placeholders.\n"
                    "- Do not use TODO comments instead of implementation.\n\n"
                    f"Application request:\n{request}\n\n"
                    f"File: {entry_point}\n\n"
                    f"Runtime error:\n{runtime_error}\n\n"
                    f"Current source code:\n{current_code}"
                )

                if (
                    not fixed_code
                    or not fixed_code.strip()
                    or fixed_code.strip().lower()
                    in {
                        "empty response received from ollama.",
                        "empty response received from ollama"
                    }
                ):
                    continue

                fixed_code = fixed_code.strip()

                # Remove accidental Markdown fences
                if fixed_code.startswith("```"):
                    lines = fixed_code.splitlines()

                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]

                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]

                    fixed_code = "\n".join(lines)

                # Save repaired source
                with open(
                    os.path.join(app_directory, entry_point),
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(fixed_code)

                # Verify repaired source before running it again
                compile_result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "py_compile",
                        os.path.join(
                            app_directory,
                            entry_point
                        )
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )

                if compile_result.returncode != 0:
                    last_runtime_error = (
                        "AI repair produced invalid Python.\n\n"
                        + compile_result.stderr.strip()
                    )
                    continue

            return {
                "reply": (
                    "Application could not be verified after "
                    f"{max_fix_attempts} repair attempts.\n\n"
                    f"Project: {project_name}\n"
                    f"Location: {app_directory}\n\n"
                    f"Last error:\n{last_runtime_error}"
                ),
                "type": "coding",
                "build_complete_application": True,
                "build_directory": app_directory,
                "generated_files": generated_files,
                "dependencies": dependencies,
                "runtime_verified": False,
                "runtime_error": last_runtime_error,
                "fix_attempts": max_fix_attempts
            }
        
        except Exception as e:
            return {
                "reply": f"Application build planning failed: {e}",
                "type": "coding"
            }

    return None
