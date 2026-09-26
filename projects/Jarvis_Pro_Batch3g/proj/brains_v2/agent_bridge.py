import brains_v2.agents
import brains_v2.tools

from brains_v2.agents.manager import process as process_agent
from brains_v2.tools.manager import process as process_tool


class AgentBridge:

    def process(self, command):

        if any(word in command.lower() for word in [
            "open",
            "launch",
            "run",
            "youtube",
            "google",
            "browser",
            "website",
            "search"
        ]):
            tool = None

        else:
            tool = process_tool(command)

        if tool is not None:

            return {

                "source": "tool",

                "result": tool

            }

        agent = process_agent(command)

        if agent is not None:

            return {

                "source": "agent",

                "result": agent

            }

        return {

            "source": "none",

            "result": None

        }


bridge = AgentBridge()