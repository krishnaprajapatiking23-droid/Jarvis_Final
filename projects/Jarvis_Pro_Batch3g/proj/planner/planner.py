from planner.goal_engine import add_goal, list_goals


def process_goal(command):

    text = command.lower()

    if text.startswith("my goal is"):

        goal = command[10:].strip()

        return add_goal(goal)

    if "what are my goals" in text:

        return list_goals()

    return None