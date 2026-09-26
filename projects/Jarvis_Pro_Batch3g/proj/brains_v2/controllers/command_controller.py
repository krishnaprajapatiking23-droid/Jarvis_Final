from brains_v2.trace import trace
from brains_v2.self_correction import self_correction
from brains_v2.correction import correction
from brains_v2.smart_commands import fix


class CommandController:

    def process(self, command):

        trace("Original :", command)

        command = correction.correct(command)

        trace("After correction :", command)

        command = fix(command)

        trace("After fix :", command)

        command = self_correction.correct(command)

        return command


command_controller = CommandController()