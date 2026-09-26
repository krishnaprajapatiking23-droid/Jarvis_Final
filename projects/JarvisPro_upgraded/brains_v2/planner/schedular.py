"""Deprecated spelling of :mod:`brains_v2.planner.scheduler` (BUG 1).

Thin backwards-compatibility wrapper only. All behaviour lives in the
canonical module, which does not import this file.
"""

import warnings

from .scheduler import *  # noqa: F401,F403
from .scheduler import __all__ as __all__  # noqa: F401

warnings.warn(
    "this module spelling is deprecated; "
    "import brains_v2.planner.scheduler instead",
    DeprecationWarning,
    stacklevel=2,
)
