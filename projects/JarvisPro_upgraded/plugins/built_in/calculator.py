"""Built-in calculator plugin.

BUG FIX: ``plugins/plugin_loader.py`` imported ``CalculatorPlugin`` from this
module, but the file only defined ``class Calculator``. The ImportError took
down ``plugin_loader`` and ``plugin_manager``, so the whole plugin system
(roadmap 36) never loaded a single plugin.

``Calculator`` and the ``calculator`` singleton are kept as aliases so any
existing caller keeps working.
"""

from __future__ import annotations

from typing import Any, Dict

from brains_v2.skills.calculator import calculate, extract_expression

from plugins.base_plugin import BasePlugin

__all__ = ["CalculatorPlugin", "Calculator", "calculator"]


class CalculatorPlugin(BasePlugin):
    """Evaluates arithmetic written in plain language."""

    name = "calculator"
    description = "Evaluates arithmetic written in plain language."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        if not any(character.isdigit() for character in text):
            return False
        expression = extract_expression(text)
        return bool(expression) and any(op in expression for op in "+-*/%")

    def execute(self, command: Any) -> Dict[str, Any]:
        return calculate(command)


# Backwards-compatible aliases.
Calculator = CalculatorPlugin
calculator = CalculatorPlugin()
