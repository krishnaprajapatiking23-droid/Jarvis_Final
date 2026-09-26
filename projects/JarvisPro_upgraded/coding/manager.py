"""
Legacy compatibility wrapper for the Jarvis Pro Coding Manager.

The main Coding Manager now lives in:
brains_v2/manager_modules/coding_manager.py

This wrapper keeps older modules such as agents/coding.py and
missions/executor.py working without maintaining a second
Coding Manager implementation.
"""

from brains_v2.manager_modules.coding_manager import process


def coding_manager(command):
    """
    Forward legacy Coding Manager calls to the main Coding Manager.
    """
    return process(command)