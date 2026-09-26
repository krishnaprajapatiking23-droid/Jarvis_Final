from brains_v2.agents.base_agent import Agent
from brains_v2.llm.manager import ask
import time


class PlannerAgent(Agent):

    name = "Planner Agent"

    description = "Creates intelligent execution plans."

    priority = 92

    KEYWORDS = {

        "plan",
        "planning",
        "roadmap",
        "strategy",
        "steps",
        "step",
        "build",
        "create",
        "develop",
        "design",
        "architecture",
        "project",
        "schedule",
        "timeline",
        "goal",
        "milestone",
        "phase",
        "workflow",
        "implementation"

    }

    def __init__(self):

        self.history = []

    def can_handle(self, command):

        text = command.lower()

        return any(word in text for word in self.KEYWORDS)

    def score(self, command):

        text = command.lower()

        score = 0

        for word in self.KEYWORDS:

            if word in text:

                score += 10

        return min(score, 100)

    def analyze_goal(self, command):

        return {

            "goal": command,

            "complexity": "High" if len(command.split()) > 8 else "Medium",

            "estimated_steps": max(4, len(command.split()) // 2)

        }

    def milestones(self):

        return [

            "Requirement Analysis",

            "Architecture",

            "Implementation",

            "Testing",

            "Optimization",

            "Deployment"

        ]

    def dependencies(self):

        return [

            "Python",

            "Required Modules",

            "Resources",

            "Testing Environment"

        ]

    def risks(self):

        return [

            "Missing dependency",

            "Logic failure",

            "Runtime error",

            "Performance issue"

        ]

    def plan(self, command):

        return [

            "Understand objective",

            "Analyze requirements",

            "Break into milestones",

            "Determine dependencies",

            "Prioritize tasks",

            "Execute",

            "Verify",

            "Optimize"

        ]

    def replan(self, command):

        return [

            "Detect failure",

            "Identify cause",

            "Modify strategy",

            "Retry execution",

            "Verify again"

        ]

    def execute(self, command):

        analysis = self.analyze_goal(command)

        prompt = f"""
You are an expert AI Project Planner.

Create a professional execution roadmap.

Goal:
{command}

Return:

1. Objective

2. Milestones

3. Dependencies

4. Risks

5. Execution Order

6. Estimated Timeline

7. Final Advice
"""

        reply = ask(prompt)

        result = {

            "success": reply is not None,

            "agent": self.name,

            "analysis": analysis,

            "plan": self.plan(command),

            "milestones": self.milestones(),

            "dependencies": self.dependencies(),

            "risks": self.risks(),

            "reply": reply if reply else "Planner model unavailable.",

            "timestamp": time.time()

        }

        self.learn(command, result)

        return result

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        self.history.append({

            "command": command,

            "success": result["success"],

            "time": result["timestamp"]

        })

    def statistics(self):

        total = len(self.history)

        success = sum(

            1

            for x in self.history

            if x["success"]

        )

        failed = total - success

        return {

            "total": total,

            "success": success,

            "failed": failed

        }


agent = PlannerAgent()