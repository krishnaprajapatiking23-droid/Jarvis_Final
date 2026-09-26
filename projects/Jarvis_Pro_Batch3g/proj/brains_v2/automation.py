from brains_v2.trace import trace
from automation.apps import open_app
from automation.browser import open_website
from automation.folders import open_folder


def execute(command, decision):
    trace("AUTOMATION.PY EXECUTED")

    if decision != "OPEN":
        return None

    result = open_folder(command)
    if result:
        return result

    result = open_app(command)
    if result:
        return result

    # Browser commands are handled by router_v2.py
    return None