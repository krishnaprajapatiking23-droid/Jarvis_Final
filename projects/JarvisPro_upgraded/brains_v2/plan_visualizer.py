"""
Plan Visualization
"""

from __future__ import annotations

from typing import Any


class PlanVisualizer:

    def build_tree(
        self,
        goal: str,
        steps: list[str],
    ) -> dict[str, Any]:

        nodes = [
            {
                "id": "goal",
                "type": "goal",
                "label": goal,
            }
        ]

        edges = []

        previous_id = "goal"

        for index, step in enumerate(steps, start=1):

            step_id = f"step_{index}"

            nodes.append(
                {
                    "id": step_id,
                    "type": "step",
                    "label": step,
                    "order": index,
                }
            )

            edges.append(
                {
                    "from": previous_id,
                    "to": step_id,
                }
            )

            previous_id = step_id

        return {
            "goal": goal,
            "nodes": nodes,
            "edges": edges,
            "step_count": len(steps),
        }

    def to_text(
        self,
        goal: str,
        steps: list[str],
    ) -> str:

        lines = [f"Goal: {goal}"]

        for index, step in enumerate(steps, start=1):
            lines.append(
                f"{index}. {step}"
            )

        return "\n".join(lines)

    def to_mermaid(
        self,
        goal: str,
        steps: list[str],
    ) -> str:

        lines = ["flowchart TD"]

        lines.append(
            f'    G["{self._escape(goal)}"]'
        )

        previous_id = "G"

        for index, step in enumerate(steps, start=1):

            step_id = f"S{index}"

            lines.append(
                f'    {step_id}["{self._escape(step)}"]'
            )

            lines.append(
                f"    {previous_id} --> {step_id}"
            )

            previous_id = step_id

        return "\n".join(lines)

    @staticmethod
    def _escape(value: str) -> str:

        return str(value).replace(
            '"',
            "'",
        )


plan_visualizer = PlanVisualizer()