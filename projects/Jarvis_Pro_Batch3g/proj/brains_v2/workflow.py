class WorkflowEngine:

    def __init__(self):

        self.workflows = {}

    def create(self, name, steps):

        self.workflows[name] = {

            "steps": steps,

            "current": 0

        }

    def next(self, name):

        if name not in self.workflows:

            return None

        workflow = self.workflows[name]

        workflow["current"] += 1

        if workflow["current"] >= len(workflow["steps"]):

            return None

        return workflow["steps"][workflow["current"]]

    def current(self, name):

        if name not in self.workflows:

            return None

        workflow = self.workflows[name]

        index = workflow["current"]

        if index >= len(workflow["steps"]):

            return None

        return workflow["steps"][index]

    def data(self):

        return self.workflows


workflow = WorkflowEngine()