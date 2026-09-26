from projects.storage import load_projects


def show_project(project):

    projects = load_projects()

    if project not in projects:
        return "Project not found."

    return projects[project]