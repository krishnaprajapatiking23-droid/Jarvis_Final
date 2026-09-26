# ==========================================
# JarvisX Configuration
# ==========================================

class Config:

    # -----------------------------
    # Project
    # -----------------------------

    NAME = "JarvisX"

    VERSION = "8.0"

    BUILD = "2026.08"

    # BUG FIX: hardcoded to the original developer's name; empty means "not
    # configured yet" rather than assuming who owns this install.
    OWNER = ""

    # -----------------------------
    # AI
    # -----------------------------

    LLM_PROVIDER = "ollama"

    LLM_MODEL = "qwen3:4b"

    TEMPERATURE = 0.7

    MAX_HISTORY = 20

    # -----------------------------
    # Voice
    # -----------------------------

    VOICE_ENABLED = False

    VOICE_LANGUAGE = "en"

    WAKE_WORD = "jarvis"

    # -----------------------------
    # Vision
    # -----------------------------

    VISION_ENABLED = False

    CAMERA_INDEX = 0

    # -----------------------------
    # Memory
    # -----------------------------

    MEMORY_ENABLED = True

    SEMANTIC_MEMORY = True

    AUTO_SAVE_MEMORY = True

    # -----------------------------
    # Automation
    # -----------------------------

    AUTOMATION_ENABLED = True

    # -----------------------------
    # Debug
    # -----------------------------

    DEBUG = True

    SHOW_RUNTIME = True

    SHOW_REASONING = True

    SHOW_ERRORS = True


config = Config()