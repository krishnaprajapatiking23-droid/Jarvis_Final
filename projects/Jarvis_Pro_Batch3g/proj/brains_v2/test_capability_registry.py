from brains_v2.tools import registry


class FakeCodingManager:

    def can_handle(self, command):
        return "code" in command.lower()

    def execute(self, command):
        return "coding result"


class FakeFileManager:

    def can_handle(self, command):
        return "file" in command.lower()

    def execute(self, command):
        return "file result"


def test_manager_capabilities_are_registered():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    coding = FakeCodingManager()

    registry.register(
        coding,
        capabilities={
            "generate_code",
            "modify_code",
            "debug_code",
        },
    )

    assert "FakeCodingManager" in registry.CAPABILITIES
    assert registry.get_capabilities(
        "FakeCodingManager"
    ) == {
        "generate_code",
        "modify_code",
        "debug_code",
    }


def test_find_manager_by_capability():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    coding = FakeCodingManager()
    files = FakeFileManager()

    registry.register(
        coding,
        capabilities={
            "generate_code",
            "modify_code",
        },
    )

    registry.register(
        files,
        capabilities={
            "create_file",
            "delete_file",
        },
    )

    matches = registry.find_by_capability(
        "generate_code"
    )

    assert len(matches) == 1
    assert isinstance(matches[0], FakeCodingManager)


def test_registry_info_returns_capabilities():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    coding = FakeCodingManager()

    registry.register(
        coding,
        capabilities={
            "generate_code",
            "debug_code",
        },
    )

    info = registry.registry_info()

    assert "FakeCodingManager" in info
    assert info["FakeCodingManager"] == [
        "debug_code",
        "generate_code",
    ]