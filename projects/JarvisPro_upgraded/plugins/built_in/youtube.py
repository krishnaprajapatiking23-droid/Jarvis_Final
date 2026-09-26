"""YouTube plugin.

This module was an empty placeholder. The capability it names already has a
single working implementation elsewhere in the project, so this file is a
documented adapter that re-exports it rather than a second copy that would
drift out of step. Import from here or from the canonical module -- both give
you the same object.

Canonical implementation: ``skills.youtube``
"""

from __future__ import annotations

from skills.youtube import YouTubeSkill as YouTubePlugin, youtube_skill as youtube_plugin

__all__ = ["YouTubePlugin", "youtube_plugin"]

