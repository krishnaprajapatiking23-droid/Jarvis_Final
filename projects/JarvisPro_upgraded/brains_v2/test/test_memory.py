"""Smoke test for the memory subsystem.

Runs standalone (``python -m brains_v2.test.test_memory``) and under pytest.
"""

from __future__ import annotations

from brains_v2.managers.memory_manager import memory_manager


def test_memory() -> None:
    assert memory_manager.capability == "memory"
    assert memory_manager.health()["available"] is True
    assert memory_manager.can_handle("remember my name is Raj")
    assert not memory_manager.can_handle("open notepad")


if __name__ == "__main__":
    test_memory()
    print("memory: OK")
