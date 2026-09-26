class GoalManager:

    def __init__(self):

        self.goal = None

        self.status = "Idle"

        self.progress = 0

    def start(self, goal):

        self.goal = goal

        self.status = "Running"

        self.progress = 0

    def update(self, value):

        self.progress = min(100, value)

        if self.progress >= 100:

            self.status = "Completed"

    def current(self):

        return {

            "goal": self.goal,

            "status": self.status,

            "progress": self.progress

        }


goal_manager = GoalManager()