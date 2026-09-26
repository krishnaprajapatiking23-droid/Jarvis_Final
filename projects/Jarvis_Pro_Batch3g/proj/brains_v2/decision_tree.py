"""
Decision Tree — secondary routing engine used by brains_v2/manager.py.
Provides more granular sub-routing after the primary decision.py pass.
"""


class DecisionTree:

    ROUTES = {
        "AUTOMATION": [
            "open", "launch", "start", "run", "execute",
            "click", "type", "press", "scroll",
        ],
        "PROJECT": [
            "build", "create", "develop", "design", "make",
            "implement", "architect", "write code",
        ],
        "MEMORY": [
            "remember", "save", "store", "note", "record",
            "remind", "recall",
        ],
        "SEARCH": [
            "search", "find", "look up", "browse", "google",
        ],
        "RESEARCH": [
            "research", "analyze", "compare", "evaluate",
            "investigate", "study",
        ],
        "CODE": [
            "code", "debug", "refactor", "review code",
            "test", "commit", "push", "git",
        ],
        "SYSTEM": [
            "shutdown", "restart", "sleep", "volume",
            "brightness", "wifi", "settings", "system",
        ],
        "FILE": [
            "file", "folder", "directory", "copy file",
            "move", "delete", "rename",
        ],
        "LEARNING": [
            "learn", "teach me", "explain", "how does",
            "what is", "why does",
        ],
        "CHAT": [],  # fallback catch-all
    }

    def decide(self, command):
        text = command.lower()
        for intent, keywords in self.ROUTES.items():
            if intent == "CHAT":
                continue  # don't match empty keyword list
            if any(word in text for word in keywords):
                return intent
        return "CHAT"


decision_tree = DecisionTree()