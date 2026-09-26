class MissionEngine:

    def __init__(self):

        self.current = None

        self.status = "Idle"

        self.completed = []

    def start(self, mission):

        self.current = mission

        self.status = "Running"

    def finish(self):

        if self.current:

            self.completed.append(self.current)

        self.current = None

        self.status = "Idle"

    def data(self):

        return {

            "current": self.current,

            "status": self.status,

            "completed": len(self.completed)

        }


mission = MissionEngine()