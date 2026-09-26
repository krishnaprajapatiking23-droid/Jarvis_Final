"""
==========================================
JARVIS PRO
Configuration
Version : 1.0
==========================================
"""

# Owner Information
#
# BUG FIX: this was hardcoded to the original developer's name ("Krishna"),
# which conversation/identity.py falls back to as its last resort when
# neither config/settings.json nor data/owner.json has a name configured --
# so every fresh install greeted its new owner by a stranger's name. Empty
# means "no name known yet"; identity.py already handles that by omitting
# the name from replies rather than guessing.
OWNER_NAME = ""

# Assistant Information
ASSISTANT_NAME = "Jarvis"

# AI Model (Ollama)
CHAT_MODEL = "qwen3:4b"

VISION_MODEL = "gemma3:12b"

# Language
DEFAULT_LANGUAGE = "en"

# Voice
VOICE_ENABLED = True

# Debug
DEBUG_MODE = True

# Application Version
VERSION = "1.0.0"

# BUG FIX: three modules (core/command_router.py, vision/image_reader.py,
# manual_demos/demo_image_reader.py) imported AI_MODEL, which was never
# defined here, so all three failed at import. It is the default chat model.
AI_MODEL = CHAT_MODEL
