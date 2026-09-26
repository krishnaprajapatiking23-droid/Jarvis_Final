"""Manual check: llm integration.

BUG FIX: this script read keys from the old ~60-key response object that
``BrainV2.process`` used to return for every command. That object is now
opt-in (it made every command pay for memory search, ranking and orchestrator
introspection), so the script enables it explicitly via JARVIS_DEBUG and reads
the ``diagnostics`` block.
"""

import os

os.environ.setdefault("JARVIS_DEBUG", "1")

from brains_v2 import process

tests = [

    "Hello",

    "What is recursion?",

    "Explain quantum computing simply.",

    "Open Notepad"

]

for command in tests:

    data = process(command)

    print()

    print("=" * 60)

    print(command)

    print()

    print("LLM Used:", data["diagnostics"]["llm_used"])

    print()

    print(data["reply"])