"""
Manager Capability Registry and Tool Registry
"""

from __future__ import annotations

from typing import Any


TOOLS: list[Any] = []
CAPABILITIES: dict[str, set[str]] = {}

REGISTERED_TOOLS: dict[str, Any] = {}
TOOL_CAPABILITIES: dict[str, set[str]] = {}


def register(tool, capabilities=None):

    TOOLS.append(tool)

    name = tool.__class__.__name__

    CAPABILITIES[name] = set(
        capabilities or []
    )


def register_tool(
    tool_name: str,
    tool: Any,
    capabilities=None,
) -> None:

    REGISTERED_TOOLS[tool_name] = tool

    TOOL_CAPABILITIES[tool_name] = set(
        capabilities or []
    )


def all_tools():

    return list(TOOLS)


def get_capabilities(manager_name: str) -> set[str]:

    return set(
        CAPABILITIES.get(manager_name, set())
    )


def find_by_capability(capability: str) -> list[Any]:

    matches = []

    for tool in TOOLS:

        name = tool.__class__.__name__

        if capability in CAPABILITIES.get(name, set()):

            matches.append(tool)

    return matches


def get_tool(tool_name: str) -> Any | None:

    return REGISTERED_TOOLS.get(tool_name)


def find_tools_by_capability(
    capability: str,
) -> list[Any]:

    matches = []

    for name, tool in REGISTERED_TOOLS.items():

        if capability in TOOL_CAPABILITIES.get(
            name,
            set(),
        ):

            matches.append(tool)

    return matches


def tool_registry_info() -> dict[str, list[str]]:

    return {
        name: sorted(capabilities)
        for name, capabilities in TOOL_CAPABILITIES.items()
    }


def registry_info() -> dict[str, list[str]]:

    return {
        name: sorted(capabilities)
        for name, capabilities in CAPABILITIES.items()
    }


from brains_v2.tools.project_scanner import project_scanner

register(
    project_scanner,
    capabilities={
        "scan_project",
        "analyze_project",
        "inspect_project",
    },
)