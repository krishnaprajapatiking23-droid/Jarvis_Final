"""
Topic Tracker (brains_v2)

Backwards-compatible layer over ``conversation.topic_tracker``.

The original version recognised six hardcoded subjects (Python, website,
Minecraft, guitar, ...). It now delegates to the Conversation System
tracker, which derives topics from tracked entities, domain keywords and
refinement words, so any subject is supported - including topic narrowing
("Python" -> "Python libraries") and explicit topic switches.

The public API (``track``, ``history``) is unchanged.
"""

import re

from conversation.topic_tracker import TopicTracker as ConversationTopicTracker

# Nouns that extend a subject into a phrase: "Python" + "website".
PHRASE_NOUNS = (
    "website",
    "site",
    "app",
    "application",
    "project",
    "code",
    "script",
    "game",
    "server",
    "bot",
    "library",
    "libraries",
    "framework",
    "frameworks",
    "tutorial",
    "tutorials",
    "file",
    "folder",
    "document",
    "model",
    "database",
)


class TopicTracker:

    def __init__(self):

        self.current_topic = ""

        self.previous_topic = ""

        self.topic_history = []

        self._engine = ConversationTopicTracker()

    def track(self, command):

        text = str(command).strip()

        if not text:
            return self._report(False)

        report = self._engine.track(
            text,
            current=self.current_topic.lower()
        )

        detected = self._display(text, str(report.get("topic") or ""))

        if not detected:
            return self._report(False)

        changed = (
            bool(self.current_topic)
            and detected.lower() != self.current_topic.lower()
        )

        if changed:
            self.previous_topic = self.current_topic

        if (
            not self.topic_history
            or self.topic_history[-1].lower() != detected.lower()
        ):
            self.topic_history.append(detected)

        self.current_topic = detected

        return self._report(changed, detected)

    def _report(self, changed, topic=None):

        return {

            "topic": self.current_topic if topic is None else topic,

            "current_topic": self.current_topic,

            "previous_topic": self.previous_topic,

            "changed": changed,

        }

    def _display(self, text, topic):
        """Present the topic using the casing the user actually typed."""

        if not topic:
            return ""

        # Unchanged topic: keep the wording already on record.
        if (
            self.current_topic
            and topic.lower() == self.current_topic.lower()
        ):
            return self.current_topic

        words = topic.split()

        match = re.search(
            rf"\b{re.escape(words[0])}\b",
            text,
            flags=re.IGNORECASE
        )

        if not match:
            return topic

        phrase = text[match.start():match.end()]

        tail = text[match.end():].lstrip()

        following = re.match(r"[A-Za-z]+", tail)

        if following and following.group(0).lower() in PHRASE_NOUNS:

            # "Python" -> "Python website"
            phrase = f"{phrase} {following.group(0)}"

        elif len(words) > 1:

            phrase = " ".join([phrase] + words[1:])

        return phrase

    def history(self):

        return list(self.topic_history)


topic_tracker = TopicTracker()
