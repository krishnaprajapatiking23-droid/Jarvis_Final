"""Compatibility shim for the retired `task` package.

Audit (Batch 3g): every module in this package was a 0-byte file and no module
anywhere in the project imported it. The authoritative task architecture is
`jarvis_core.tasks` (TaskManager / TaskStore / Task), which is the one wired
into the kernel.

The package is kept only so that any out-of-tree caller keeps working; it
re-exports the real implementation and warns once on import. It contains no
task logic of its own.
"""

import warnings

from jarvis_core.tasks import StateError, Task, TaskManager, TaskStore

warnings.warn(
    "`task` is deprecated and now only re-exports jarvis_core.tasks; "
    "import from jarvis_core.tasks directly.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Task", "TaskManager", "TaskStore", "StateError"]
