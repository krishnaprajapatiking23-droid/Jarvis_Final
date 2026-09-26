"""
Task Dependency Graph
"""

from __future__ import annotations

from collections import defaultdict, deque


class DependencyGraph:

    def __init__(self):
        self.dependencies: dict[str, set[str]] = defaultdict(set)

    def add_task(self, task: str) -> None:
        self.dependencies.setdefault(task, set())

    def add_dependency(
        self,
        task: str,
        depends_on: str,
    ) -> None:

        self.add_task(task)
        self.add_task(depends_on)

        if task == depends_on:
            raise ValueError(
                "A task cannot depend on itself"
            )

        if self._creates_cycle(task, depends_on):
            raise ValueError(
                "Dependency would create a cycle"
            )

        self.dependencies[task].add(depends_on)

    def get_dependencies(
        self,
        task: str,
    ) -> list[str]:

        return sorted(
            self.dependencies.get(task, set())
        )

    def get_ready_tasks(
        self,
        completed: set[str] | None = None,
    ) -> list[str]:

        completed = completed or set()

        ready = []

        for task, dependencies in self.dependencies.items():

            if task in completed:
                continue

            if dependencies.issubset(completed):
                ready.append(task)

        return sorted(ready)

    def execution_order(self) -> list[str]:

        graph: dict[str, set[str]] = {
            task: set(dependencies)
            for task, dependencies in self.dependencies.items()
        }

        order = []

        while graph:

            ready = sorted(
                task
                for task, dependencies in graph.items()
                if not dependencies
            )

            if not ready:
                raise ValueError(
                    "Dependency graph contains a cycle"
                )

            order.extend(ready)

            for task in ready:
                del graph[task]

            for dependencies in graph.values():
                dependencies.difference_update(ready)

        return order

    def _creates_cycle(
        self,
        task: str,
        depends_on: str,
    ) -> bool:

        queue = deque([depends_on])
        visited = set()

        while queue:

            current = queue.popleft()

            if current == task:
                return True

            if current in visited:
                continue

            visited.add(current)

            queue.extend(
                self.dependencies.get(
                    current,
                    set(),
                )
            )

        return False

    def to_dict(self) -> dict[str, list[str]]:

        return {
            task: sorted(dependencies)
            for task, dependencies in self.dependencies.items()
        }


dependency_graph = DependencyGraph()