"""
Jarvis Agent Manager V2
"""

from brains_v2.agents.registry import all_agents

def process(command):

    candidates = []

    for agent in all_agents():

        if not getattr(agent, "enabled", True):
            continue

        try:
            score = agent.score(command)
        except Exception:
            score = 100 if agent.can_handle(command) else 0

        if score > 0:
            candidates.append((score, agent.priority, agent))

    if not candidates:
        return {
            "success": False,
            "reply": "No suitable agent found."
        }

    candidates.sort(
        key=lambda x: (x[0], x[1]),
        reverse=True
    )

    errors = []

    for score, priority, agent in candidates:

        try:

            result = agent.run(command)

            if result and result.get("success", False):
                result["selected_agent"] = agent.name
                result["score"] = score
                return result

        except Exception as e:

            errors.append({
                "agent": agent.name,
                "error": str(e)
            })

    return {
        "success": False,
        "reply": "No agent could complete the task.",
        "errors": errors
    }


def available_agents():

    return [agent.info() for agent in all_agents()]


def statistics():

    return [agent.stats() for agent in all_agents()]