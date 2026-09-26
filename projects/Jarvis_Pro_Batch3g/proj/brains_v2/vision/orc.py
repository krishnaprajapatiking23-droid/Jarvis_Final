"""Deprecated spelling of :mod:`brains_v2.vision.ocr` (BUG 1).

Thin backwards-compatibility wrapper only; the canonical module does not
import this file.
"""

import warnings

from .ocr import *  # noqa: F401,F403
from .ocr import __all__ as __all__  # noqa: F401

warnings.warn(
    "this module spelling is deprecated; import brains_v2.vision.ocr instead",
    DeprecationWarning,
    stacklevel=2,
)
