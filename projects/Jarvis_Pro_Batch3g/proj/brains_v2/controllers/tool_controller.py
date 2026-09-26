from brains_v2.tools.manager import process


class ToolController:

    def process(self, command):

        result = process(command)

        if result:
            return result

        return None


tool_controller = ToolController() 