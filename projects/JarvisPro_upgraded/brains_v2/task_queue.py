from __future__ import annotations

from heapq import heappop, heappush


class TaskQueue:

    def __init__(self):

        self.queue = []
        self._counter = 0

    def add(self, task, priority=5):

        priority = max(1, min(10, int(priority)))

        item = {
            "task": task,
            "priority": priority,
            "order": self._counter
        }

        heappush(
            self.queue,
            (-priority, self._counter, item)
        )

        self._counter += 1

    def next(self):

        if not self.queue:
            return None

        return heappop(self.queue)[2]

    def peek(self):

        if not self.queue:
            return None

        return self.queue[0][2]

    def clear(self):

        self.queue.clear()
        self._counter = 0

    def size(self):

        return len(self.queue)

    def all(self):

        return [item[2] for item in sorted(self.queue)]

    def prioritize(self, task, priority):

        priority = max(1, min(10, int(priority)))

        items = self.all()

        self.clear()

        for item in items:

            if item["task"] == task:
                item["priority"] = priority

            self.add(
                item["task"],
                item["priority"]
            )


task_queue = TaskQueue()