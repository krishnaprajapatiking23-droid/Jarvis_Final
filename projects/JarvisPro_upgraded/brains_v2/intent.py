import re
"""
Jarvis V6 Intent Engine
"""

INTENTS = {

    "automation": [
        "open",
        "close",
        "launch",
        "run",
        "start",
        "stop",
        "kill",
        "restart",

        "notepad",
        "calculator",
        "calc",
        "paint",
        "cmd",
        "terminal",
        "explorer",
        "control panel"
    ],

    "browser": [
        "browser",
        "chrome",
        "edge",
        "firefox",

        "website",
        "web",

        "youtube",
        "google",
        "gmail",
        "amazon",
        "facebook",
        "instagram",
        "twitter",
        "linkedin",

        "search",
        "visit"
    ],

    "desktop": [
        "desktop",
        "folder",
        "file",
        "documents",
        "downloads"
    ],

    "windows": [
        "window",
        "minimize",
        "maximize",
        "restore",
        "switch"
    ],

    "memory": [
        "remember",
        "recall",
        "forget",
        "save",
        "store",
        "my name"
    ],

    "knowledge": [
        "what",
        "who",
        "why",
        "how",
        "when",
        "where",
        "explain",
        "tell"
    ],

    "coding": [
        "code",
        "python",
        "java",
        "javascript",
        "html",
        "css",
        "api",
        "program"
    ],

    "research": [
        "research",
        "investigate",
        "analyze",
        "study",
        "compare"
    ],

    "business": [
        "business",
        "marketing",
        "shopify",
        "dropshipping",
        "profit",
        "sales"
    ],

    "vision": [
        "screen",
        "screenshot",
        "image",
        "photo",
        "ocr",
        "camera",
        "detect",
        "recognize",
        "what is on my screen",
        "read my screen",
        "look at my screen"
    ],

    "internet": [
        "internet",
        "online",
        "news",
        "weather"
    ],

    "security": [
        "lock",
        "unlock",
        "owner",
        "permission",
        "permissions",
        "secure",
        "security",
        "password",
        "audit",
        "safe mode"
    ],

    "mobile": [
        "phone",
        "android",
        "sms",
        "companion",
        "paired",
        "notification",
        "notifications"
    ],

    "notes": [
        "note",
        "notes",
        "add note",
        "show notes",
        "read note",
        "delete note",
        "clear notes"
    ],

    "task": [
        "task",
        "todo",
        "remind",
        "schedule",
        "mission"
    ],

    "conversation": [
        "hello",
        "hi",
        "thanks",
        "thank you",
        "good morning",
        "good evening"
    ],

    "exit": [
        "exit",
        "quit",
        "shutdown",
        "bye",
        "goodbye"
    ]
}


def detect(command):
    """Classify ``command`` into one of the INTENTS buckets.

    BUG FIX: scoring used bare substring tests (``word in command``), so
    "call" matched "recall", "ai" matched "again" and "note" matched
    "notepad" -- while "security status" matched nothing at all because the
    keyword list held "secure". Matching is now on whole words, with exact
    and prefix matches still weighted higher.
    """
    text = (command or "").lower().strip()

    if not text:
        return "conversation"

    best = "conversation"
    score = 0

    for intent, words in INTENTS.items():

        current = 0

        for word in words:

            word = word.lower()

            if text == word:
                current += 4

            elif text.startswith(word + " "):
                current += 3

            elif " " in word:
                # Multi-word phrases are matched as a phrase.
                if word in text:
                    current += 2

            elif re.search(r"\b%s(?:e?s)?\b" % re.escape(word), text):
                # BUG FIX: a plain \bword\b never matched the plural, because
                # "s" is a word character. "Show my running task" routed to
                # the task manager while "Show my running tasks" fell through
                # to chat. The optional suffix covers task/tasks,
                # note/notes, reminder/reminders and so on.
                current += 1

        if current > score:
            score = current
            best = intent

    return best