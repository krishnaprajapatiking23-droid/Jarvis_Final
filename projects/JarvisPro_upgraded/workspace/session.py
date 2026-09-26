from workspace.state import workspace


def start_session(project):

    workspace["project"] = project

    return f"Workspace started for {project}."


def current_project():

    return workspace["project"]