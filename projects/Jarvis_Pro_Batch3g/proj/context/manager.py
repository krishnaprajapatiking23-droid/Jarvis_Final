from context.window import active_window
from context.apps import app_running


def get_context():

    return {

        "window": active_window(),

        "notepad": app_running("notepad"),

        "chrome": app_running("chrome"),

        "explorer": app_running("explorer")

    }