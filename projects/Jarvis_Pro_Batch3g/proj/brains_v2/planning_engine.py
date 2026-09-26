class PlanningEngine:

    def create(self, command):

        text = command.lower()

        if "build" in text:

            return [

                "Analyze requirements",

                "Design architecture",

                "Write code",

                "Test modules",

                "Deploy"

            ]

        if "create" in text:

            return [

                "Understand request",

                "Generate solution",

                "Verify output"

            ]

        return [

            "Understand",

            "Execute"

        ]


planning_engine = PlanningEngine()