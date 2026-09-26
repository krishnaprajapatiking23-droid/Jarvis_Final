"""Jarvis Pro application entry point.

BUG 1: the brain is created once by JarvisRuntime and injected into the
pipeline, so Application -> BrainV2 -> Pipeline -> input -> response all share
one instance.
BUG 2: commands go through JarvisRuntime.process(), which calls the canonical
BrainV2.process() API.
BUG 3: initialize() prints the per-service startup report and the
"Jarvis is online." greeting (or the reason it could not start).
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional

from brains_v2.runtime import JarvisRuntime, get_runtime


class Jarvis:
    """Thin application shell around the injected runtime."""

    def __init__(self, runtime: Optional[JarvisRuntime] = None) -> None:
        self.runtime = runtime or get_runtime()
        self.mode: Optional[str] = None
        self.report: Dict[str, Any] = {}

    @staticmethod
    def _prepare_storage() -> None:
        for label, module_name, attribute in (
            ("scheduler", "scheduler.scheduler", "run"),
            ("memory tables", "memory.database", "create_tables"),
            ("visitor tables", "memory.visitor_database", "create_tables"),
            ("conversation tables", "conversation.store", "create_tables"),
        ):
            try:
                module = importlib.import_module(module_name)
                getattr(module, attribute)()
            except Exception as error:
                print("[~] %s unavailable: %s" % (label, error))

    def initialize(self, interactive: bool = True) -> Dict[str, Any]:
        print("=" * 10 + " JARVIS PRO " + "=" * 10)
        self._prepare_storage()
        try:
            startup = importlib.import_module("brains_v2.startup")
            startup.startup()
        except Exception as error:
            print("[~] startup banner unavailable: %s" % error)
        self.report = self.runtime.start().to_dict()
        if interactive and self.report.get("online"):
            try:
                startup = importlib.import_module("brains_v2.startup")
                self.mode = startup.choose_mode()
            except (EOFError, KeyboardInterrupt):
                self.mode = "text"
            except Exception as error:
                print("[~] mode selection unavailable: %s" % error)
                self.mode = "text"
        else:
            self.mode = self.mode or "text"
        return self.report

    def process(self, text: str) -> Any:
        """Single command entry point used by the GUI, voice and Android."""
        return self.runtime.process(text)

    def start(self, interactive: bool = True) -> Any:
        if not self.report:
            self.initialize(interactive=interactive)
        if not self.report.get("online"):
            return self.report
        return self.runtime.pipeline().run(self.mode or "text")

    def shutdown(self) -> None:
        self.runtime.shutdown()


def main() -> Any:
    jarvis = Jarvis()
    try:
        return jarvis.start()
    finally:
        jarvis.shutdown()


if __name__ == "__main__":
    main()
