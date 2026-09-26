from projects.storage import load_projects, save_projects


def add_task(project, task):

    projects = load_projects()

    if project not in projects:
        return "Project not found."

    projects[project]["tasks"].append(task)

    save_projects(projects)

    return f"Task added to {project}."