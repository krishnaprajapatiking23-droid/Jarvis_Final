from engine.planner import create_execution_plan
from engine.executor import execute
from engine.validator import validate
from engine.logger import log


def jarvis_engine(command, username):

    plan = create_execution_plan(command)

    log("Execution Plan")

    for step in plan:

        log(step)

    answer = execute(command, username)

    if not validate(answer):

        return "Execution failed."

    return answer