"""Arithmetic skill.

BUG FIX (two bugs in one file):

* ``brains_v2/skills/__init__.py`` imported ``CalculatorSkill`` from here, but
  this module only defined a bare ``calculate()`` function. Because the bad
  import lived in the package ``__init__``, *every* module in
  ``brains_v2.skills`` failed to import (9 modules) and the whole skill
  registry was dead.
* ``calculate("what is 25 * 4")`` returned "only numeric arithmetic is
  allowed", because the raw sentence was handed straight to the evaluator.
  The arithmetic is now extracted from natural language first.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from security.safe_math import SafeMathError, evaluate

from brains_v2.skills.skill import Skill

__all__ = ["CalculatorSkill", "calculate", "extract_expression"]

_WORD_OPERATORS = (
    (r"\bplus\b", "+"),
    (r"\badded to\b", "+"),
    (r"\bminus\b", "-"),
    (r"\btake away\b", "-"),
    (r"\btimes\b", "*"),
    (r"\bmultiplied by\b", "*"),
    (r"\bdivided by\b", "/"),
    (r"\bmodulo\b", "%"),
    (r"\bmod\b", "%"),
    (r"\bto the power of\b", "**"),
    (r"\bsquared\b", "**2"),
    (r"\bcubed\b", "**3"),
)

_PREFIXES = re.compile(
    r"^\s*(?:hey\s+|ok\s+|please\s+|jarvis[,\s]+)*"
    r"(?:what(?:'s| is)|whats|how much is|calculate|compute|evaluate|solve|work out)?"
    r"\s*",
    re.IGNORECASE,
)

_EXPRESSION = re.compile(r"[-+(]?\s*\d[\d\s.,]*(?:[-+*/%()]+\s*\d[\d\s.,]*)+\)?")

_TRIGGER = re.compile(
    r"\b(calculate|compute|evaluate|solve|plus|minus|times|multiplied|divided|"
    r"squared|cubed|modulo)\b",
    re.IGNORECASE,
)


def extract_expression(command: Any) -> Optional[str]:
    """Pull a bare arithmetic expression out of a natural-language command.

    ``"what is 25 * 4"`` -> ``"25 * 4"``; ``"12 plus 5"`` -> ``"12 + 5"``.
    Returns ``None`` when the text contains no arithmetic at all.
    """
    text = str(command or "").strip()
    if not text:
        return None

    text = text.rstrip("?!. ")
    text = _PREFIXES.sub("", text, count=1)

    for pattern, symbol in _WORD_OPERATORS:
        text = re.sub(pattern, symbol, text, flags=re.IGNORECASE)

    match = _EXPRESSION.search(text)
    if not match:
        return None

    expression = match.group(0)
    expression = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expression)
    expression = expression.replace(",", " ")
    expression = re.sub(r"\s+", " ", expression).strip()

    opened = expression.count("(")
    closed = expression.count(")")
    if closed > opened:
        expression = expression.replace(")", "", closed - opened)
    elif opened > closed:
        expression += ")" * (opened - closed)

    return expression or None


def calculate(command: Any) -> Dict[str, Any]:
    """Evaluate the arithmetic in ``command``. Always returns a dict."""
    expression = extract_expression(command)

    if expression is None:
        return {
            "success": False,
            "error": "no arithmetic expression found",
            "reply": "I couldn't find a sum in that.",
        }

    try:
        value = evaluate(expression)
    except SafeMathError as error:
        return {
            "success": False,
            "error": str(error),
            "expression": expression,
            "reply": "I can't work that out: %s." % error,
        }
    except Exception as error:
        return {
            "success": False,
            "error": "%s: %s" % (type(error).__name__, error),
            "expression": expression,
            "reply": "I can't work that out.",
        }

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return {
        "success": True,
        "expression": expression,
        "result": value,
        "reply": "%s = %s" % (expression, value),
    }


class CalculatorSkill(Skill):
    """Skill wrapper so the registry can discover arithmetic."""

    name = "calculator"
    description = "Evaluates arithmetic written in plain language."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        if not any(character.isdigit() for character in text):
            return False
        expression = extract_expression(text)
        if not expression:
            return False
        return any(op in expression for op in "+-*/%")

    def execute(self, command: Any) -> Dict[str, Any]:
        return calculate(command)
