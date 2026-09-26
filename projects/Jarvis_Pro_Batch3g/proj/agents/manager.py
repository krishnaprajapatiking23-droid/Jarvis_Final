from agents.business import business_agent
from agents.coding import coding_agent


AGENTS = {
    "business": business_agent,
    "coding": coding_agent,
}


def run_agent(agent, command):

    agent = agent.lower()

    if agent not in AGENTS:
        return f"Unknown agent: {agent}"

    return AGENTS[agent](command)