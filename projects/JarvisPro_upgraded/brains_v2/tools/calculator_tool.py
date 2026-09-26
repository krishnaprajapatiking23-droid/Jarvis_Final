from brains_v2.tools.base_tool import Tool
from security.safe_math import evaluate

class CalculatorTool(Tool):
    name = "Calculator Tool"
    description = "Evaluate numeric arithmetic without eval."

    def can_handle(self, command):
        text = str(command or "").lower()
        return "calculate" in text or any(op in text for op in ("+", "-", "*", "/"))

    def execute(self, command):
        expression = str(command or "").lower().replace("calculate", "").strip()
        try:
            return {"success": True, "result": evaluate(expression)}
        except Exception as error:
            return {"success": False, "error": str(error)}

def calculate(command):
    return CalculatorTool().execute(command)
