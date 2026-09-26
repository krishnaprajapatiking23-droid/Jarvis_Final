"""Translator plugin.

This module was an empty placeholder. The capability it names already has a
single working implementation elsewhere in the project, so this file is a
documented adapter that re-exports it rather than a second copy that would
drift out of step. Import from here or from the canonical module -- both give
you the same object.

Canonical implementation: ``skills.translator``
"""

from __future__ import annotations

from skills.translator import TranslatorSkill as TranslatorPlugin, translator_skill as translator_plugin

__all__ = ["TranslatorPlugin", "translator_plugin"]

