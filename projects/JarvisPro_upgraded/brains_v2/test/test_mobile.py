"""Smoke test for the mobile subsystem.

Runs standalone (``python -m brains_v2.test.test_mobile``) and under pytest.
"""

from __future__ import annotations

from brains_v2.core_bridge import handle_mobile


def test_mobile() -> None:
    result = handle_mobile("phone status")
    assert isinstance(result, dict) and result["reply"]
    assert "pair" in result["reply"].lower() or "device" in result["reply"].lower()


if __name__ == "__main__":
    test_mobile()
    print("mobile: OK")
