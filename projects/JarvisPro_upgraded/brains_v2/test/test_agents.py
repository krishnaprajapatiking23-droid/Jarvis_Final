"""Smoke test for the agents subsystem.

Runs standalone (``python -m brains_v2.test.test_agents``) and under pytest.
"""

from __future__ import annotations

import brains_v2.agents as agents


def test_agents() -> None:
    assert agents.names(), "no agents registered"
    assert agents.select("open notepad").name == "desktop"
    assert agents.select("research black holes").name == "research"
    assert agents.select("hello there").name == "conversation"


if __name__ == "__main__":
    test_agents()
    print("agents: OK")
