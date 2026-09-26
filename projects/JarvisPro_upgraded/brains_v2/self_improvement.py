class SelfImprovement:

    def __init__(self):

        self.version = "2.0"

        self.improvements = []

    def learn(self, command, verification):

        if not verification["success"]:

            self.improvements.append(

                f"Improve handling of: {command}"

            )

    def suggestions(self):

        return self.improvements[-10:]

    def report(self):

        return {

            "version": self.version,

            "pending": len(self.improvements),

            "items": self.suggestions()

        }


self_improvement = SelfImprovement()