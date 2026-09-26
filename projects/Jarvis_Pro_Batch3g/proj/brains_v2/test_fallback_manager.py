from brains_v2.tools.manager import ManagerOrchestrator
from brains_v2.tools import registry


class PrimaryManager:

    def can_handle(self, command):
        return True

    def execute(self, command):
        return "Primary executed"


class FallbackManager:

    def can_handle(self, command):
        return True

    def execute(self, command):
        return "Fallback executed"


def test_fallback_manager_is_selected():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    primary = PrimaryManager()
    fallback = FallbackManager()

    registry.register(
        primary,
        capabilities={"execute"},
    )

    registry.register(
        fallback,
        capabilities={"execute"},
    )

    orchestrator = ManagerOrchestrator()
    orchestrator.managers = [
        primary,
        fallback,
    ]

    result = orchestrator.select_fallback_manager(
        "execute",
        preferred_manager="PrimaryManager",
    )

    assert result["status"] == "fallback_selected"
    assert result["manager"] == "FallbackManager"


def test_no_fallback_is_reported_when_none_exists():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    primary = PrimaryManager()

    registry.register(
        primary,
        capabilities={"execute"},
    )

    orchestrator = ManagerOrchestrator()
    orchestrator.managers = [primary]

    result = orchestrator.select_fallback_manager(
        "missing_capability",
        preferred_manager="PrimaryManager",
    )

    assert result["status"] == "no_fallback"
    assert result["manager"] is None


def test_preferred_manager_is_excluded_from_fallback():
    registry.TOOLS.clear()
    registry.CAPABILITIES.clear()

    primary = PrimaryManager()
    fallback = FallbackManager()

    registry.register(
        primary,
        capabilities={"execute"},
    )

    registry.register(
        fallback,
        capabilities={"execute"},
    )

    orchestrator = ManagerOrchestrator()
    orchestrator.managers = [
        primary,
        fallback,
    ]

    result = orchestrator.select_fallback_manager(
        "execute",
        preferred_manager="PrimaryManager",
    )

    assert result["manager"] != "PrimaryManager"
    assert result["manager"] == "FallbackManager"