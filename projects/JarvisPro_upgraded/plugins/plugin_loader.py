from plugins.built_in.calculator import CalculatorPlugin

plugins = [
    CalculatorPlugin()
]


def load_plugins():
    return plugins