"""Smoke test for the voice subsystem.

Runs standalone (``python -m brains_v2.test.test_voice``) and under pytest.
"""

from __future__ import annotations

from brains_v2.speech.wakeword import detect


def test_voice() -> None:
    awake = detect("hey jarvis open notepad")
    assert awake["awake"] and awake["command"] == "open notepad"
    assert not detect("the weather is nice today")["awake"]


if __name__ == "__main__":
    test_voice()
    print("voice: OK")
