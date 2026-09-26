class HonestyEngine:

    def answer(self, success):

        if success:

            return None

        return (
            "I couldn't complete that task successfully. "
            "I won't pretend that I did."
        )

    def correct(self, text):

        mistakes = {

            "nut pad": "Notepad",

            "calclator": "Calculator",

            "chrme": "Chrome",

            "pain": "Paint"

        }

        lower = text.lower()

        for wrong, right in mistakes.items():

            if wrong in lower:

                return (
                    f"Did you mean '{right}'?"
                )

        return None


honesty = HonestyEngine()