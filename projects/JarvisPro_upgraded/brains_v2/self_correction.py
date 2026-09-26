"""
Jarvis Pro Self Correction Engine
"""


class SelfCorrection:

    def __init__(self):

        self.total = 0
        self.corrected = 0

    def correct(self, command):

        self.total += 1

        if not isinstance(command, str):
            return ""

        command = command.strip()

        return command

    def statistics(self):

        return {

            "total": self.total,

            "corrected": self.corrected

        }


self_correction = SelfCorrection()