from projects.storage import load_projects, save_projects


def complete_task(project, task):

    projects = load_projects()

    if project not in projects:
        return "Project not found."

    if task in projects[project]["tasks"]:

        projects[project]["tasks"].remove(task)

        projects[project]["completed"].append(task)

        save_projects(projects)

        return "Task completed."

    return "Task not found."