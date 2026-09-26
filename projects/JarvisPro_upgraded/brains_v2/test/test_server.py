"""Smoke test for the server subsystem.

Runs standalone (``python -m brains_v2.test.test_server``) and under pytest.
"""

from __future__ import annotations

from brains_v2.networking.connection import free_port, local_ip


def test_server() -> None:
    port = free_port()
    assert 1 <= port <= 65535
    assert local_ip()
    assert free_port(port) == port or free_port(port) > 0


if __name__ == "__main__":
    test_server()
    print("server: OK")
