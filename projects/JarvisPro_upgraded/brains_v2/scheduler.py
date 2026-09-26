import time


class Scheduler:

    def __init__(self):

        self.jobs = []

    def add(self, task):

        self.jobs.append({

            "task": task,

            "time": time.strftime("%H:%M:%S")

        })

    def latest(self):

        if not self.jobs:

            return None

        return self.jobs[-1]

    def all(self):

        return self.jobs

    def total(self):

        return len(self.jobs)


scheduler = Scheduler()