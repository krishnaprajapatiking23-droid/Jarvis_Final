import time


class RePlanner:

    def __init__(self):

        self.failed_plans = []

    def record_failure(self, goal, plan, reason):

        failure = {
            "goal": goal,
            "plan": plan,
            "reason": reason,
            "time": time.time()
        }

        self.failed_plans.append(failure)

        return failure

    def generate(self, goal, previous_plan=None):

        plan = {
            "goal": goal,
            "steps": [
                f"Analyse goal: {goal}",
                "Choose the best strategy",
                "Execute each step",
                "Verify the result",
                "Retry if necessary"
            ],
            "previous_plan": previous_plan,
            "created": time.time()
        }

        return plan

    def replan(self, goal, previous_plan, reason):

        self.record_failure(goal, previous_plan, reason)

        new_plan = self.generate(goal, previous_plan)

        new_plan["retry_reason"] = reason
        new_plan["attempt"] = len(self.failed_plans)

        return new_plan

    def history(self):

        return self.failed_plans

    def clear(self):

        self.failed_plans.clear()

        return True


replanner = RePlanner()