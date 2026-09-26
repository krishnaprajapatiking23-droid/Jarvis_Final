from workspace.state import workspace


def open_file(filename):

    workspace["last_file"] = filename

    return f"Working on {filename}."


def last_file():

    return workspace["last_file"]