"""Arithmetic skill for the top-level skills package.

Delegates to the single implementation in
:mod:`brains_v2.skills.calculator` so there is one parser, not two that drift
apart. Exposes the ``process_*`` shape ``skills/skill_manager.py`` expects.
"""

from __future__ import annotations

from typing import Any, Optional

from brains_v2.skills.calculator import calculate, extract_expression

__all__ = ["process_calculator", "calculate", "extract_expression"]


def process_calculator(command: Any) -> Optional[str]:
    """Return the answer sentence, or None when there is no arithmetic."""
    expression = extract_expression(command)

    if not expression or not any(op in expression for op in "+-*/%"):
        return None

    result = calculate(command)
    return result.get("reply") if result.get("success") else None
