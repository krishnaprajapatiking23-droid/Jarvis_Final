"""Manual check: manager.

BUG FIX: this script read keys from the old ~60-key response object that
``BrainV2.process`` used to return for every command. That object is now
opt-in (it made every command pay for memory search, ranking and orchestrator
introspection), so the script enables it explicitly via JARVIS_DEBUG and reads
the ``diagnostics`` block.
"""

import os

os.environ.setdefault("JARVIS_DEBUG", "1")

from brains_v2.manager import brain

brain.process("Open Notepad")

brain.process("Open Calculator")

brain.process("Hello")

data = brain.process("Open Paint")

print()

print(data["diagnostics"]["brain_state"])