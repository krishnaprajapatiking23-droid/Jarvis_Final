"""
Dynamic Task Planner
"""

from __future__ import annotations

from brains_v2.decomposer import decomposer


class Planner:

    def create_plan(self, command):

        command = str(command).strip()

        steps = decomposer.decompose(command)

        return {
            "goal": command,
            "steps": steps,
            "step_count": len(steps),
            "dynamic": True
        }


planner = Planner()