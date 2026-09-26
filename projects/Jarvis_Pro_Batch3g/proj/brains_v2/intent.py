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
        "image",
        "photo",
        "ocr",
        "camera",
        "detect",
        "recognize"
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
        "secure",
        "password"
    ],

    "mobile": [
        "phone",
        "android",
        "sms",
        "call",
        "notification"
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

    command = command.lower()

    best = "conversation"

    score = 0

    for intent, words in INTENTS.items():

        current = 0

        for word in words:

            if command == word:
                current += 3

            elif command.startswith(word):
                current += 2

            elif word in command:
                current += 1

        if current > score:

            score = current

            best = intent

    return best