"""Thinking manager.

This module was an empty placeholder. The capability it names already has a
single working implementation elsewhere in the project, so this file is a
documented adapter that re-exports it rather than a second copy that would
drift out of step. Import from here or from the canonical module -- both give
you the same object.

Canonical implementation: ``brains_v2.ai.reasoning``
"""

from __future__ import annotations

from brains_v2.ai.reasoning import Reasoner, reasoner

__all__ = ["Reasoner", "reasoner"]

