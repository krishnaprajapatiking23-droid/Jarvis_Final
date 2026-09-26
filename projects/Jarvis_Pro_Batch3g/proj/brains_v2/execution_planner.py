class ExecutionPlanner:

    def __init__(self):

        self.plan = []

    def build(self, tasks):

        self.plan = []

        for i, task in enumerate(tasks, start=1):

            self.plan.append({

                "step": i,

                "task": task,

                "status": "Pending"

            })

    def complete(self):

        for item in self.plan:

            if item["status"] == "Pending":

                item["status"] = "Completed"

                break

    def current(self):

        for item in self.plan:

            if item["status"] == "Pending":

                return item

        return None

    def all(self):

        return self.plan


execution_planner = ExecutionPlanner()