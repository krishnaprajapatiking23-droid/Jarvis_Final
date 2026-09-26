class CorrectionEngine:

    def __init__(self):

        self.corrections = {

            "nut pad": "notepad",

            "note pad": "notepad",

            "calclator": "calculator",

            "calcultor": "calculator",

            "chrme": "chrome",

            "googel": "google"

        }

    def correct(self, command):

        text = command.lower()

        for wrong, correct in self.corrections.items():

            if wrong in text:

                return text.replace(wrong, correct)

        return command


correction = CorrectionEngine()