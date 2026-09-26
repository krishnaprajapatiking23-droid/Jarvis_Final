class AutonomousCore:

    def __init__(self):

        self.state = "Idle"

        self.current_goal = None

    def start(self, goal):

        self.state = "Working"

        self.current_goal = goal

    def stop(self):

        self.state = "Idle"

        self.current_goal = None

    def report(self):

        return {

            "state": self.state,

            "goal": self.current_goal

        }


autonomous_core = AutonomousCore()