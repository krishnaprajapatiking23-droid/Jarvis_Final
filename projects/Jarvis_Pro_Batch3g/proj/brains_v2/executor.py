class Executor:

    def __init__(self):

        self.steps = []

        self.current = -1

    def load(self, tasks):

        self.steps = list(tasks)

        self.current = 0 if self.steps else -1

    def current_step(self):

        if self.current == -1:

            return None

        if self.current >= len(self.steps):

            return None

        return self.steps[self.current]

    def next(self):

        self.current += 1

        if self.current >= len(self.steps):

            return None

        return self.steps[self.current]

    def finished(self):

        return self.current >= len(self.steps)


executor = Executor()