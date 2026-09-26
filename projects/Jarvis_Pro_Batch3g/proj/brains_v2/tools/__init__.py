from brains_v2.tools.registry import register

from brains_v2.tools.app_tool import AppTool
from brains_v2.tools.browser_tool import BrowserTool
from brains_v2.tools.calculator_tool import CalculatorTool

register(AppTool())
register(BrowserTool())
register(CalculatorTool())