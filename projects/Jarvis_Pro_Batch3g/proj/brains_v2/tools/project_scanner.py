import os


class ProjectScanner:

    name = "project_scanner"

    def can_handle(self, command):

        command = command.lower()

        return any(x in command for x in (
            "scan project",
            "project scan",
            "analyze project",
            "project report"
        ))

    def execute(self, command):

        root = os.getcwd()

        os.makedirs("docs", exist_ok=True)

        output = []

        for path, dirs, files in os.walk(root):

            if "__pycache__" in path:
                continue

            if ".git" in path:
                continue

            output.append(path)

            for file in files:

                if file.endswith(".py"):
                    output.append("    " + file)

        with open("docs/ARCHITECTURE.md", "w", encoding="utf-8") as f:
            f.write("\n".join(output))

        return {
            "reply": "Architecture generated successfully."
        }


project_scanner = ProjectScanner()