class BrainPipeline:

    def __init__(self):

        self.steps = []

    def add(self, step):

        self.steps.append(step)

    def execute(self, data):

        current = data

        for step in self.steps:

            current = step(current)

            if current is None:
                return None

        return current


pipeline = BrainPipeline()