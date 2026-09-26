from brains_v2.psychology.personality import (
    get_personality,
    update_trait,
    reset_personality
)


def test_personality_update_and_reset():
    reset_personality()

    initial = get_personality()

    update_trait("confidence", 10)
    update_trait("curiosity", 5)

    updated = get_personality()

    assert updated["confidence"] == initial["confidence"] + 10
    assert updated["curiosity"] == initial["curiosity"] + 5

    reset_personality()

    restored = get_personality()

    assert restored == initial