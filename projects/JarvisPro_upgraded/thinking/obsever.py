"""Deprecated spelling of :mod:`thinking.observer` (BUG 1).

Thin backwards-compatibility wrapper only; the canonical module does not
import this file.
"""

import warnings

from .observer import *  # noqa: F401,F403
from .observer import __all__ as __all__  # noqa: F401

warnings.warn(
    "this module spelling is deprecated; import thinking.observer instead",
    DeprecationWarning,
    stacklevel=2,
)
