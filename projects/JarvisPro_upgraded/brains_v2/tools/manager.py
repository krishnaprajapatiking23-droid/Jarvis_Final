"""
Manager Orchestration, Communication, and Fallback Manager Selection
"""

from __future__ import annotations

from typing import Any

from brains_v2.tools.registry import (
    all_tools,
    find_by_capability,
)


class ManagerMessage:

    def __init__(
        self,
        sender: str,
        receiver: str,
        command: str,
        data: Any = None,
    ):
        self.sender = sender
        self.receiver = receiver
        self.command = command
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "command": self.command,
            "data": self.data,
        }


class ManagerOrchestrator:

    def __init__(self):
        self.managers = list(all_tools())
        self.message_history: list[dict[str, Any]] = []

    def find_managers(
        self,
        command: str,
    ) -> list[Any]:

        return [
            manager
            for manager in self.managers
            if manager.can_handle(command)
        ]

    def select_fallback_manager(
        self,
        capability: str,
        preferred_manager: str | None = None,
    ) -> dict[str, Any]:

        candidates = find_by_capability(
            capability
        )

        if preferred_manager:
            candidates = [
                manager
                for manager in candidates
                if manager.__class__.__name__
                != preferred_manager
            ]

        if not candidates:
            return {
                "status": "no_fallback",
                "capability": capability,
                "manager": None,
            }

        selected = candidates[0]

        return {
            "status": "fallback_selected",
            "capability": capability,
            "manager": selected.__class__.__name__,
        }

    def send_message(
        self,
        sender: str,
        receiver: str,
        command: str,
        data: Any = None,
    ) -> dict[str, Any]:

        message = ManagerMessage(
            sender=sender,
            receiver=receiver,
            command=command,
            data=data,
        )

        message_data = message.to_dict()

        self.message_history.append(
            message_data
        )

        target = next(
            (
                manager
                for manager in self.managers
                if manager.__class__.__name__
                == receiver
            ),
            None,
        )

        if target is None:
            return {
                "status": "receiver_not_found",
                "message": message_data,
            }

        result = target.execute(command)

        return {
            "status": "delivered",
            "message": message_data,
            "result": result,
        }

    def communication_history(
        self,
    ) -> list[dict[str, Any]]:

        return list(self.message_history)

    def orchestrate(
        self,
        command: str,
    ) -> dict[str, Any]:

        managers = self.find_managers(command)

        if not managers:
            return {
                "command": command,
                "status": "no_manager",
                "manager_count": 0,
                "results": [],
            }

        results = []

        for manager in managers:

            result = manager.execute(command)

            results.append(
                {
                    "manager":
                        manager.__class__.__name__,
                    "result": result,
                }
            )

        return {
            "command": command,
            "status": "completed",
            "manager_count": len(managers),
            "results": results,
        }


orchestrator = ManagerOrchestrator()


def process(command: str):

    managers = orchestrator.find_managers(command)

    if not managers:
        return None

    if len(managers) == 1:
        return managers[0].execute(command)

    return orchestrator.orchestrate(command)