from core.intent import detect_intent
from brains.manager import brain_manager
from brains_v2 import process as brain_v2_process
from core.brain_selector import active
from missions.manager import mission_manager
from planner.planner import process_goal
from planner.task_engine import plan
from skills.skill_manager import process_skill
from automation.apps import open_app
from automation.browser import open_website
from automation.folders import open_folder
from automation.file_manager import create_folder
from plugins.plugin_manager import process_plugin
from memory.memory_engine import process_memory
from security.permissions import has_system_access
from ai.action_classifier import classify
from ai.action_executor import execute


def route_command(user, username):

    # ==================================
    # Empty Command Protection
    # ==================================
    user = user.strip()

    if not user:
        return "Please type or say a command."

    intent = detect_intent(user)

    # ==================================
    # Memory
    # ==================================
    result = process_memory(user)

    if result:
        return result

    # ==================================
    # Goals
    # ==================================
    goal = process_goal(user)

    if goal:
        return goal

    # ==================================
    # Task Planner
    # ==================================
    task = plan(user)

    if task:
        return task

    # ==================================
    # Plugins
    # ==================================
    plugin = process_plugin(user)

    if plugin:
        return plugin

    # ==================================
    # Permission Check
    # ==================================
    if intent in ["open", "create_folder"]:

        if not has_system_access(username):

            return (
                f"Sorry {username}. "
                "Only the owner can control this computer."
            )

    # ==================================
    # Open Commands
    # ==================================
#    if intent == "open":
#
#        result = open_folder(user)
#
#        if result:
#            return result
#
#        result = open_app(user)
#
#    if result:
#
#        from brains.response import response
#
#        return response(result)
#
#        result = open_website(user)
#
#        if result:
#            return result

    # ==================================
    # Create Folder
    # ==================================
    if intent == "create_folder":

        result = create_folder(user)

        if result:
            return result

    # ==================================
    # Skills
    # ==================================
    skill = process_skill(user)

    if skill:
        return skill

    # ==================================
    # AI Action Engine
    # ==================================
#    action = classify(user)
#
#    result = execute(action)
#
#    if result:
#        return result

    # ==================================
    # Mission Detection
    # ==================================
    mission_words = [
        "build",
        "create",
        "launch",
        "start",
        "grow",
        "develop",
        "plan"
    ]

    if any(word in user.lower() for word in mission_words):
        return mission_manager(user)

    # ==================================
    # Universal Brain Manager
    # ==================================
    if active():

        result = brain_v2_process(user)

        from brains_v2.reply_text import reply_text

        return reply_text(result)

    return brain_manager(user, username)