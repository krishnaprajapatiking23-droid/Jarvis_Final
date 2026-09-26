from projects.project import create_project
from projects.tasks import add_task
from projects.progress import complete_task
from projects.notes import show_project


def project_manager(command):

    text = command.lower().strip()

    # ============================
    # Create Project
    # ============================
    if text.startswith("create project"):

        name = command[len("Create Project"):].strip()

        return create_project(name)

    # ============================
    # Add Task
    # ============================
    elif text.startswith("add task"):

        data = command[len("Add Task"):].strip()

        parts = data.split(",", 1)

        if len(parts) != 2:
            return "Use:\nAdd Task Project Name, Task"

        project = parts[0].strip()
        task = parts[1].strip()

        return add_task(project, task)

    # ============================
    # Complete Task
    # ============================
    elif text.startswith("complete task"):

        data = command[len("Complete Task"):].strip()

        parts = data.split(",", 1)

        if len(parts) != 2:
            return "Use:\nComplete Task Project Name, Task"

        project = parts[0].strip()
        task = parts[1].strip()

        return complete_task(project, task)

    # ============================
    # Show Project
    # ============================
    elif text.startswith("show project"):

        name = command[len("Show Project"):].strip()

        return show_project(name)

    return "Unknown project command."