from brains_v2.psychology.personality import (
    get_personality,
    reset_personality
)

from brains_v2.psychology.behavior import record_behavior


def test_behavior():

    reset_personality()

    initial = get_personality()

    assert initial is not None

    behaviors = [
        "studied",
        "completed_task",
        "built_project",
        "exercise"
    ]

    for behavior in behaviors:
        result = record_behavior(behavior)

        assert result is True

    final = get_personality()

    assert final is not None
    assert final != initial