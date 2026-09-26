from workspace.session import start_session
from workspace.files import open_file
from workspace.context import show_context


def workspace_manager(command):

    text = command.lower()

    if text.startswith("workspace"):

        name = command[len("workspace"):].strip()

        return start_session(name)

    elif text.startswith("file"):

        name = command[len("file"):].strip()

        return open_file(name)

    elif text == "context":

        return show_context()

    return None