"""
Decision Engine — maps user commands to intent categories.
Used by brains_v2/manager.py to route requests correctly.
"""


class DecisionEngine:

    # Intent keyword sets — add more patterns here as needed
    INTENT_PATTERNS = {
        "OPEN": [
            "open", "launch", "start", "run", "execute",
            "youtube", "google", "chrome", "browser",
            "notepad", "calculator", "terminal", "explorer",
            "screenshot", "desktop", "window", "app",
            "spotify", "vscode", "code", "file",
        ],
        "AUTOMATION": [
            "click", "type", "press", "scroll", "swipe",
            "key", "hotkey", "shortcut", "macro",
            "automate", "do it", "handle this",
        ],
        "PROJECT": [
            "build", "create", "develop", "design", "write code",
            "make", "implement", "architect", "plan project",
        ],
        "MEMORY": [
            "remember", "save", "store", "note", "record",
            "remind", "forget", "recall", "forgot",
            "what did i say", "my name", "i am",
        ],
        "SEARCH": [
            "search", "find", "look up", "google", "browse",
            "web search", "internet", "online", "query",
        ],
        "RESEARCH": [
            "research", "analyze", "compare", "evaluate",
            "investigate", "study", "learn about",
        ],
        "CODE": [
            "code", "debug", "refactor", "review",
            "test", "commit", "push", "git", "function",
        ],
        "SYSTEM": [
            "shutdown", "restart", "sleep", "hibernate",
            "volume", "brightness", "wifi", "bluetooth",
            "settings", "preferences", "system",
        ],
        "FILE": [
            "file", "folder", "directory", "copy", "move",
            "delete", "rename", "download", "upload",
        ],
        "LEARN": [
            "learn", "teach me", "explain", "how does",
            "what is", "why does", "understand",
        ],
    }

    def execute(self, command):
        command_lower = command.lower()
        for intent, keywords in self.INTENT_PATTERNS.items():
            if any(kw in command_lower for kw in keywords):
                return intent
        return "CHAT"


decision = DecisionEngine()


def decide(command):
    return decision.execute(command)