"""Smoke test for the desktop subsystem.

Runs standalone (``python -m brains_v2.test.test_desktop``) and under pytest.
"""

from __future__ import annotations

from brains_v2.managers.automation_manager import automation_manager


def test_desktop() -> None:
    assert automation_manager.capability == "automation"
    assert not automation_manager.can_handle("tell me a joke")
    report = automation_manager.health()
    assert set(report) >= {"available", "capability", "detail"}


if __name__ == "__main__":
    test_desktop()
    print("desktop: OK")
