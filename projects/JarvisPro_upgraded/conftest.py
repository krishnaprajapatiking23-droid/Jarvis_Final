"""Pytest configuration.

Makes the project root importable so tests can ``import conversation`` and
``import brains_v2`` regardless of how pytest is invoked.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
