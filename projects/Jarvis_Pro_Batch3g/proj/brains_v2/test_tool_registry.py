from brains_v2.tools import registry


class FakeTool:

    def execute(self, command):
        return f"Executed: {command}"


def test_tool_can_be_registered():
    registry.REGISTERED_TOOLS.clear()
    registry.TOOL_CAPABILITIES.clear()

    tool = FakeTool()

    registry.register_tool(
        "test_tool",
        tool,
        capabilities={
            "search",
            "execute",
        },
    )

    assert registry.get_tool("test_tool") is tool


def test_tool_can_be_found_by_capability():
    registry.REGISTERED_TOOLS.clear()
    registry.TOOL_CAPABILITIES.clear()

    search_tool = FakeTool()
    other_tool = FakeTool()

    registry.register_tool(
        "search_tool",
        search_tool,
        capabilities={"search"},
    )

    registry.register_tool(
        "other_tool",
        other_tool,
        capabilities={"execute"},
    )

    matches = registry.find_tools_by_capability(
        "search"
    )

    assert len(matches) == 1
    assert matches[0] is search_tool


def test_tool_registry_info_returns_capabilities():
    registry.REGISTERED_TOOLS.clear()
    registry.TOOL_CAPABILITIES.clear()

    tool = FakeTool()

    registry.register_tool(
        "test_tool",
        tool,
        capabilities={
            "execute",
            "search",
        },
    )

    info = registry.tool_registry_info()

    assert "test_tool" in info
    assert info["test_tool"] == [
        "execute",
        "search",
    ]