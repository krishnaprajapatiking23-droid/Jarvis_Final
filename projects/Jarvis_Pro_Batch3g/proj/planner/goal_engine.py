import json
import os

GOAL_FILE = "data/goals.json"


def load_goals():

    if not os.path.exists(GOAL_FILE):
        return []

    with open(GOAL_FILE, "r") as file:
        return json.load(file)


def save_goals(goals):

    with open(GOAL_FILE, "w") as file:
        json.dump(goals, file, indent=4)


def add_goal(goal):

    goals = load_goals()

    if goal not in goals:
        goals.append(goal)

    save_goals(goals)

    return "Goal added successfully."


def list_goals():

    goals = load_goals()

    if not goals:
        return "You don't have any goals yet."

    text = "YOUR GOALS\n\n"

    for i, goal in enumerate(goals, 1):
        text += f"{i}. {goal}\n"

    return text