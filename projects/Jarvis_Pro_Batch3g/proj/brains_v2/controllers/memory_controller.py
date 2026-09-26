from brains_v2.intents.memory_intent import detect as detect_memory

from brains_v2.memory.memory import (
    remember,
    recall,
    update_profile,
    get_profile,
    add_person,
    get_people,
)


class MemoryController:

    def process(self, command):

        memory_intent = detect_memory(command)

        if not memory_intent:
            return None

        intent_type = memory_intent["type"]

        # -------------------------
        # People
        # -------------------------

        if intent_type == "add_person":
            return {
                "reply": add_person(memory_intent["value"])
            }

        if intent_type == "list_people":

            people = get_people()

            if not people:
                return {
                    "reply": "You haven't introduced anyone yet."
                }

            return {
                "reply": "Your friends are: " + ", ".join(people)
            }

        # -------------------------
        # Profile
        # -------------------------

        if intent_type == "set_name":
            return {
                "reply": update_profile(
                    "name",
                    memory_intent["value"]
                )
            }

        if intent_type == "get_name":

            name = get_profile("name")

            if not name:
                return {
                    "reply": "I don't know your name yet."
                }

            return {
                "reply": f"Your name is {name}."
            }

        if intent_type == "set_age":
            return {
                "reply": update_profile(
                    "age",
                    memory_intent["value"]
                )
            }

        if intent_type == "get_age":

            age = get_profile("age")

            if not age:
                return {
                    "reply": "I don't know your age yet."
                }

            return {
                "reply": f"You are {age}."
            }

        # -------------------------
        # Memory
        # -------------------------

        if intent_type == "goal":
            return {
                "reply": remember(
                    "goals",
                    memory_intent["text"]
                )
            }

        if intent_type == "preference":
            return {
                "reply": remember(
                    "preferences",
                    memory_intent["text"]
                )
            }

        if intent_type == "remember_fact":

            stored = remember(
                "facts",
                memory_intent["text"]
            )

            # The same message usually asks something too ("Remember that
            # my project is called JARVIS. What is my project called?").
            # Save the fact, then let the conversation system answer the
            # question instead of swallowing it.
            if memory_intent.get("question"):
                return None

            return {"reply": stored}

        if intent_type == "recall_goals":

            goals = recall("goals")

            if not goals:
                return {
                    "reply": "You haven't shared any goals yet."
                }

            return {
                "reply": "\n".join(goals)
            }

        return None


memory_controller = MemoryController()