"""
Business Module — thin wrapper exposing the business_manager singleton.
Used by business/planner.py (line 1: from business.business import business).
"""

from business.manager import business_manager


class Business:
    """Facade for business operations."""

    def __init__(self):
        self._manager = business_manager

    def process(self, command):
        return self._manager.process(command)

    def route(self, command):
        return self._manager.route(command)

    def analyze(self, command):
        return self._manager.analyze(command)

    def report(self):
        return self._manager.report()


business = Business()
