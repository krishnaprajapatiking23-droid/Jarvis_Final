"""Bounded arithmetic evaluator (BUG 4).

The previous guard only rejected ``abs(exponent) > 100``, so nested powers
still reached the interpreter. Protection is now *static*: the expression is
inspected and rejected **before** any value is computed, so a hostile
expression can never monopolise the CPU. Limits are general (depth,
operation count, operand/exponent magnitude, nesting, result digits) rather
than a blacklist of specific strings.
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Any, Dict, Type

__all__ = ["SafeMathError", "Limits", "LIMITS", "evaluate", "safe_eval"]


class SafeMathError(ValueError):
    """Raised for unsafe or unsupported expressions."""


@dataclass(frozen=True)
class Limits:
    """Static resource limits applied before evaluation."""

    max_expression_length: int = 512
    max_ast_depth: int = 20
    max_operations: int = 64
    max_pow_nesting: int = 1
    max_exponent: int = 1024
    max_pow_base: float = 1e12
    max_result_digits: int = 1000
    max_abs_value: float = 1e308


LIMITS = Limits()

BINARY_OPS: Dict[Type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPS: Dict[Type[ast.unaryop], Any] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _digits(value: Any) -> int:
    """Approximate decimal digit count without materialising the number."""
    try:
        magnitude = abs(float(value))
    except (TypeError, ValueError, OverflowError):
        return LIMITS.max_result_digits + 1
    if magnitude < 1:
        return 1
    try:
        return int(math.log10(magnitude)) + 1
    except (ValueError, OverflowError):
        return LIMITS.max_result_digits + 1


def _number(node: ast.AST) -> Any:
    """Return the literal value of a (possibly negated) numeric constant."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        inner = _number(node.operand)
        if inner is None:
            return None
        return UNARY_OPS[type(node.op)](inner)
    return None


def _check_magnitude(value: Any, label: str, limits: Limits) -> None:
    try:
        magnitude = abs(value)
    except TypeError:
        raise SafeMathError("only numeric arithmetic is allowed")
    if isinstance(magnitude, int):
        if magnitude and _digits(magnitude) > limits.max_result_digits:
            raise SafeMathError(f"{label} exceeds the safe digit limit")
        return
    if math.isinf(magnitude) or math.isnan(magnitude):
        raise SafeMathError(f"{label} is not a finite number")
    if magnitude > limits.max_abs_value:
        raise SafeMathError(f"{label} exceeds the safe magnitude limit")


def _guard_power(node: ast.BinOp, limits: Limits) -> None:
    """Statically bound a ``**`` node before it is ever evaluated."""
    exponent = _number(node.right)
    if exponent is None:
        raise SafeMathError("exponent must be a literal number")
    if abs(exponent) > limits.max_exponent:
        raise SafeMathError(
            f"exponent magnitude exceeds the safe limit ({limits.max_exponent})"
        )

    base = _number(node.left)
    if base is None:
        if abs(exponent) > 64:
            raise SafeMathError("exponent too large for a computed base")
        return
    if abs(base) > limits.max_pow_base:
        raise SafeMathError("power base exceeds the safe magnitude limit")
    if base and abs(exponent) * _digits(base) > limits.max_result_digits:
        raise SafeMathError("result would exceed the safe digit limit")


def _inspect(node: ast.AST, limits: Limits) -> None:
    """Walk the tree once, enforcing depth, count and power limits."""
    operations = 0

    def walk(current: ast.AST, depth: int, pow_depth: int) -> None:
        nonlocal operations
        if depth > limits.max_ast_depth:
            raise SafeMathError("expression is too deeply nested")

        if isinstance(current, ast.Expression):
            walk(current.body, depth + 1, pow_depth)
            return

        if isinstance(current, ast.Constant):
            if type(current.value) not in (int, float):
                raise SafeMathError("only numeric arithmetic is allowed")
            _check_magnitude(current.value, "operand", limits)
            return

        if isinstance(current, ast.UnaryOp):
            if type(current.op) not in UNARY_OPS:
                raise SafeMathError("only numeric arithmetic is allowed")
            operations += 1
            walk(current.operand, depth + 1, pow_depth)
            return

        if isinstance(current, ast.BinOp):
            if type(current.op) not in BINARY_OPS:
                raise SafeMathError("only numeric arithmetic is allowed")
            operations += 1
            if operations > limits.max_operations:
                raise SafeMathError("expression contains too many operations")
            if isinstance(current.op, ast.Pow):
                next_pow = pow_depth + 1
                if next_pow > limits.max_pow_nesting:
                    raise SafeMathError("nested exponentiation is not allowed")
                _guard_power(current, limits)
                walk(current.left, depth + 1, next_pow)
                walk(current.right, depth + 1, next_pow)
                return
            walk(current.left, depth + 1, pow_depth)
            walk(current.right, depth + 1, pow_depth)
            return

        raise SafeMathError("only numeric arithmetic is allowed")

    walk(node, 0, 0)


def evaluate(expression: Any, limits: Limits = LIMITS) -> Any:
    """Evaluate a numeric expression, or raise :class:`SafeMathError`."""
    text = str(expression).strip()
    if not text:
        raise SafeMathError("empty expression")
    if len(text) > limits.max_expression_length:
        raise SafeMathError("expression is too long")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as error:
        raise SafeMathError(f"invalid expression: {error.msg}")

    _inspect(tree, limits)

    def compute(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return compute(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp):
            return UNARY_OPS[type(node.op)](compute(node.operand))
        if isinstance(node, ast.BinOp):
            left = compute(node.left)
            right = compute(node.right)
            try:
                value = BINARY_OPS[type(node.op)](left, right)
            except ZeroDivisionError:
                raise SafeMathError("division by zero")
            except (OverflowError, MemoryError):
                raise SafeMathError("result is too large to compute")
            _check_magnitude(value, "result", limits)
            return value
        raise SafeMathError("only numeric arithmetic is allowed")

    return compute(tree)


def safe_eval(expression: Any) -> Any:
    """Backwards-compatible alias for :func:`evaluate`."""
    return evaluate(expression)
