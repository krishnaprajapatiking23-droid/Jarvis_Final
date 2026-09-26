from brains_v2.agents.registry import register

from brains_v2.agents.coding_agent import CodingAgent
from brains_v2.agents.research_agent import ResearchAgent
from brains_v2.agents.planner_agent import PlannerAgent
from brains_v2.agents.automation_agent import AutomationAgent
from brains_v2.agents.conversation_agent import ConversationAgent
from brains_v2.agents.memory_agent import MemoryAgent
from brains_v2.agents.security_agent import SecurityAgent

register(CodingAgent())
register(ResearchAgent())
register(PlannerAgent())
register(AutomationAgent())
register(ConversationAgent())
register(MemoryAgent())
register(SecurityAgent())