from projects.storage import load_projects, save_projects


def create_project(name):

    projects = load_projects()

    if name in projects:
        return "Project already exists."

    projects[name] = {
        "tasks": [],
        "completed": []
    }

    save_projects(projects)

    return f"Project '{name}' created."