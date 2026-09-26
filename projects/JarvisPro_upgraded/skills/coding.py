"""Coding skill: local static checks that need no model.

Syntax checking, formatting hints and simple metrics for Python source, so
"is this valid python?" and "check my file" work offline.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import Any, Dict, List, Optional

__all__ = ["CodingSkill", "coding_skill", "process_coding_skill"]

_TRIGGER = re.compile(
    r"\b(check|validate|lint|analyse|analyze|is\s+this\s+valid)\b.*"
    r"\b(code|python|syntax|script|file)\b",
    re.IGNORECASE,
)


class CodingSkill:
    name = "coding"
    description = "Offline Python syntax checking and code metrics."

    def can_handle(self, command: Any) -> bool:
        return bool(_TRIGGER.search(str(command or "")))

    # -- analysis ----------------------------------------------------
    def check_syntax(self, source: str) -> Dict[str, Any]:
        try:
            ast.parse(source)
        except SyntaxError as error:
            return {
                "valid": False,
                "line": error.lineno,
                "offset": error.offset,
                "message": error.msg,
            }
        return {"valid": True}

    def metrics(self, source: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {"parsed": False}

        functions = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        imports = [n for n in ast.walk(tree)
                   if isinstance(n, (ast.Import, ast.ImportFrom))]
        lines = source.splitlines()

        return {
            "parsed": True,
            "lines": len(lines),
            "code_lines": sum(1 for line in lines
                              if line.strip() and not line.strip().startswith("#")),
            "functions": len(functions),
            "classes": len(classes),
            "imports": len(imports),
            "undocumented_functions": [
                f.name for f in functions if not ast.get_docstring(f)
            ],
            "max_line_length": max((len(line) for line in lines), default=0),
        }

    def style_warnings(self, source: str) -> List[str]:
        warnings: List[str] = []
        for number, line in enumerate(source.splitlines(), start=1):
            if len(line) > 99:
                warnings.append("line %d is %d characters" % (number, len(line)))
            if line.rstrip() != line:
                warnings.append("line %d has trailing whitespace" % number)
            if "\t" in line:
                warnings.append("line %d uses a tab for indentation" % number)
        try:
            list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (tokenize.TokenError, IndentationError) as error:
            warnings.append("tokenizer: %s" % error)
        return warnings[:50]

    def execute(self, source: str) -> Dict[str, Any]:
        syntax = self.check_syntax(source)
        report: Dict[str, Any] = {"success": syntax["valid"], "syntax": syntax}

        if not syntax["valid"]:
            report["reply"] = ("Syntax error on line %s: %s"
                               % (syntax["line"], syntax["message"]))
            return report

        report["metrics"] = self.metrics(source)
        report["warnings"] = self.style_warnings(source)
        report["reply"] = (
            "Valid Python: %d lines, %d function(s), %d class(es), %d warning(s)."
            % (report["metrics"]["lines"], report["metrics"]["functions"],
               report["metrics"]["classes"], len(report["warnings"]))
        )
        return report


coding_skill = CodingSkill()


def process_coding_skill(source: str) -> Optional[str]:
    if not source:
        return None
    return coding_skill.execute(source).get("reply")
