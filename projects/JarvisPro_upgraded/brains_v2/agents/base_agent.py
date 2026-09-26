"""
Jarvis Agent V2
Backward Compatible
"""

from abc import ABC
import time


class Agent(ABC):

    # ----------------------------
    # Basic Information
    # ----------------------------

    name = "Base Agent"
    description = ""
    version = "2.0"

    # Higher number = higher priority
    priority = 50

    # ----------------------------
    # Configuration
    # ----------------------------

    enabled = True
    memory_access = True
    allow_parallel = False

    required_tools = []
    dependencies = []

    # ----------------------------
    # Runtime Statistics
    # ----------------------------

    def __init__(self):

        self.calls = 0
        self.success = 0
        self.failed = 0
        self.total_time = 0.0

    # ----------------------------
    # Detection
    # ----------------------------

    def can_handle(self, command):

        return False

    # ----------------------------
    # Confidence
    # ----------------------------

    def score(self, command):

        if self.can_handle(command):
            return 100

        return 0

    # ----------------------------
    # Planning
    # ----------------------------

    def plan(self, command):

        return []

    # ----------------------------
    # Main Execution
    # ----------------------------

    def execute(self, command):

        return None

    # ----------------------------
    # Verification
    # ----------------------------

    def verify(self, result):

        return result is not None

    # ----------------------------
    # Learning
    # ----------------------------

    def learn(self, command, result):

        pass

    # ----------------------------
    # Safe Execute
    # ----------------------------

    def run(self, command):

        start = time.perf_counter()

        self.calls += 1

        try:

            result = self.execute(command)

            if self.verify(result):

                self.success += 1

            else:

                self.failed += 1

            self.learn(command, result)

            return result

        except Exception as e:

            self.failed += 1

            return {
                "success": False,
                "error": str(e)
            }

        finally:

            self.total_time += (
                time.perf_counter() - start
            )

    # ----------------------------
    # Statistics
    # ----------------------------

    def stats(self):

        rate = 0

        if self.calls:

            rate = round(
                self.success * 100 / self.calls,
                2
            )

        return {

            "name": self.name,

            "version": self.version,

            "priority": self.priority,

            "calls": self.calls,

            "success": self.success,

            "failed": self.failed,

            "success_rate": rate,

            "average_time": round(
                self.total_time / max(1, self.calls),
                4
            )
        }

    # ----------------------------
    # Information
    # ----------------------------

    def info(self):

        return {

            "name": self.name,

            "description": self.description,

            "priority": self.priority,

            "enabled": self.enabled,

            "required_tools": self.required_tools,

            "dependencies": self.dependencies
        }