import time
from collections import defaultdict


class Optimizer:

    def __init__(self):

        self.metrics = defaultdict(list)

    def record(self, operation, duration, success=True):

        self.metrics[operation].append({
            "duration": duration,
            "success": success,
            "timestamp": time.time()
        })

    def average_time(self, operation):

        records = self.metrics.get(operation, [])

        if not records:
            return 0

        return round(
            sum(r["duration"] for r in records) / len(records),
            3
        )

    def success_rate(self, operation):

        records = self.metrics.get(operation, [])

        if not records:
            return 0

        success = sum(
            1 for r in records
            if r["success"]
        )

        return round(
            success * 100 / len(records),
            2
        )

    def suggest(self, operation):

        avg = self.average_time(operation)

        rate = self.success_rate(operation)

        suggestions = []

        if avg > 5:

            suggestions.append(
                "Operation is slow. Consider optimizing or caching."
            )

        if rate < 90:

            suggestions.append(
                "Operation fails frequently. Improve error handling."
            )

        if not suggestions:

            suggestions.append(
                "Performance is healthy."
            )

        return suggestions

    def report(self):

        report = {}

        for operation in self.metrics:

            report[operation] = {

                "runs": len(self.metrics[operation]),

                "average_time": self.average_time(operation),

                "success_rate": self.success_rate(operation),

                "suggestions": self.suggest(operation)

            }

        return report

    # ============================================
    # Learning Engine
    # ============================================

    def learn(self, command, verification):

        self.record(
            "learning",
            0,
            verification.get("success", True)
            if isinstance(verification, dict)
            else True
        )

        return True

    # ============================================
    # Runtime Update
    # ============================================

    def update(self):

        return True
    

    def clear(self):

        self.metrics.clear()

        return True


optimizer = Optimizer()