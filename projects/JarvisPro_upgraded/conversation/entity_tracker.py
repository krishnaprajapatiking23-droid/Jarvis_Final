"""
==========================================
JARVIS PRO
Entity Tracker  (feature 3.21)
==========================================

Extracts and tracks the things a conversation is about:
people, companies, apps, places, projects and objects.

Detection is deterministic (no network, no model required) and combines:
  * curated vocabularies for apps / companies / places / projects
  * the app table from ``automation.apps`` when it is importable
  * capitalised-phrase heuristics for unseen people and companies

Every entity is returned as::

    {"name": "Chrome", "type": "app", "text": "chrome", "context": "..."}
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger("jarvis.conversation.entities")

PERSON = "person"
COMPANY = "company"
APP = "app"
PLACE = "place"
PROJECT = "project"
OBJECT = "object"
TOPIC = "topic"

# ------------------------------------------------------------------
# vocabularies
# ------------------------------------------------------------------
BASE_APPS: Set[str] = {
    "chrome", "edge", "firefox", "brave", "opera", "safari",
    "notepad", "wordpad", "calculator", "paint", "cmd", "powershell",
    "terminal", "explorer", "vs code", "vscode", "visual studio code",
    "word", "excel", "powerpoint", "outlook", "spotify", "youtube",
    "whatsapp", "telegram", "discord", "steam", "settings",
    "task manager", "file explorer", "camera", "photos", "clock",
}

COMPANIES: Set[str] = {
    "tesla", "microsoft", "google", "apple", "amazon", "meta", "facebook",
    "openai", "anthropic", "nvidia", "intel", "amd", "spacex", "netflix",
    "twitter", "x", "ibm", "oracle", "samsung", "sony", "reliance",
    "tata", "infosys", "wipro", "adobe", "notion", "github",
}

PEOPLE: Set[str] = {
    "elon musk", "bill gates", "steve jobs", "jeff bezos", "mark zuckerberg",
    "sundar pichai", "satya nadella", "sam altman", "tim cook",
    "narendra modi", "albert einstein", "isaac newton", "nikola tesla",
    "guido van rossum", "linus torvalds", "ada lovelace", "alan turing",
}

PLACES: Set[str] = {
    "mumbai", "ahmedabad", "delhi", "bangalore", "bengaluru", "pune",
    "chennai", "kolkata", "hyderabad", "surat", "jaipur", "gujarat",
    "india", "usa", "america", "london", "new york", "california",
    "tokyo", "paris", "dubai", "singapore", "canada", "germany",
}

PROJECTS: Set[str] = {
    "jarvis", "jarvis pro", "python project", "this project",
}

OBJECTS: Set[str] = {
    "file", "folder", "document", "note", "reminder", "screenshot",
    "window", "tab", "script", "database", "function", "class",
    "report", "email", "image", "video", "song", "playlist",
}

TECH_TOPICS: Set[str] = {
    "python", "javascript", "typescript", "java", "c++", "c#", "rust",
    "go", "golang", "php", "ruby", "swift", "kotlin", "sql", "html",
    "css", "react", "django", "flask", "fastapi", "numpy", "pandas",
    "tensorflow", "pytorch", "machine learning", "deep learning",
    "artificial intelligence", "data science", "web development",
}

# Words that look like names but are never entities.
STOPWORDS: Set[str] = {
    "i", "me", "my", "you", "your", "jarvis", "ok", "okay", "yes", "no",
    "the", "a", "an", "and", "or", "but", "so", "then", "now", "please",
    "what", "who", "when", "where", "why", "how", "which", "tell", "open",
    "close", "good", "morning", "afternoon", "evening", "night", "hello",
    "hi", "hey", "thanks", "thank", "sure", "actually", "meant", "sorry",
    "is", "it", "this", "that", "about", "for", "from", "with", "can",
    "could", "would", "should", "do", "does", "did", "was", "were", "are",
    "am", "be", "been", "of", "in", "on", "at", "to", "by",
    "let", "lets", "explain", "remember", "create", "send", "show",
    "give", "make", "summarize", "summarise", "describe", "start",
    "keep", "here", "there", "also", "just", "well", "going",
}

# Vocabulary words that are usually something else in plain English.
# "Go back to ..." is the verb, not the language.
AMBIGUOUS_TERMS = {
    "go": (
        "golang",
        "go language",
        "go programming",
        "in go",
        "using go",
        "go code",
        "learn go",
        "go vs",
        "and go",
    ),
}


def _ambiguous_is_meant(lowered: str, term: str) -> bool:
    """True when an ambiguous vocabulary word really is the entity."""
    cues = AMBIGUOUS_TERMS.get(term)
    if not cues:
        return True
    return any(cue in lowered for cue in cues)

ALIASES: Dict[str, str] = {
    "vscode": "VS Code",
    "vs code": "VS Code",
    "visual studio code": "VS Code",
    "bengaluru": "Bangalore",
    "golang": "Go",
    "facebook": "Meta",
    "ai": "artificial intelligence",
    "ml": "machine learning",
}

_TITLE_PATTERN = re.compile(r"\b([A-Z][a-z]{2,})(?:\s+([A-Z][a-z]{2,}))?\b")


def _load_project_apps() -> Set[str]:
    """Pull app names from the existing automation layer when available."""
    names: Set[str] = set()
    try:  # pragma: no cover - depends on host project state
        from automation.apps import APPS  # type: ignore

        names.update(str(key).lower() for key in APPS.keys())
    except Exception as error:
        log.debug("automation.apps unavailable: %s", error)
    return names


APPS: Set[str] = BASE_APPS | _load_project_apps()

VOCABULARY: List[tuple[Set[str], str]] = [
    (PEOPLE, PERSON),
    (PROJECTS, PROJECT),
    (APPS, APP),
    (COMPANIES, COMPANY),
    (PLACES, PLACE),
    (TECH_TOPICS, TOPIC),
    (OBJECTS, OBJECT),
]


def _display_name(raw: str) -> str:
    lowered = raw.strip().lower()
    if lowered in ALIASES:
        return ALIASES[lowered]
    if lowered in TECH_TOPICS or lowered in OBJECTS:
        return lowered if len(lowered) > 3 else lowered.upper()
    return " ".join(part.capitalize() for part in lowered.split())


class EntityTracker:
    """Extracts entities from text and keeps a rolling memory of them."""

    def __init__(self) -> None:
        self.seen: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    def extract(self, text: str) -> List[Dict[str, Any]]:
        """Return every entity mentioned in ``text``, longest match first."""
        if not text or not text.strip():
            return []

        lowered = f" {text.lower().strip()} "
        found: List[Dict[str, Any]] = []
        claimed: List[tuple[int, int]] = []

        candidates: List[tuple[str, str]] = []
        for vocabulary, type in VOCABULARY:
            for term in vocabulary:
                candidates.append((term, type))
        candidates.sort(key=lambda pair: len(pair[0]), reverse=True)

        for term, type in candidates:
            for match in re.finditer(rf"(?<![\w]){re.escape(term)}(?![\w])", lowered):
                span = (match.start(), match.end())
                if any(span[0] < end and start < span[1] for start, end in claimed):
                    continue
                if not _ambiguous_is_meant(lowered, term):
                    continue
                claimed.append(span)
                found.append(
                    {
                        "name": _display_name(term),
                        "type": type,
                        "text": term,
                        "context": text.strip()[:200],
                    }
                )
                break

        found.extend(self._guess_proper_nouns(text, found))

        # Preserve mention order within the sentence.
        found.sort(key=lambda entity: lowered.find(entity["text"]))
        return found

    # ------------------------------------------------------------------
    def _guess_proper_nouns(
        self, text: str, already: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Heuristic detection of unknown people/companies from capitalisation."""
        known = {entity["text"] for entity in already}
        guesses: List[Dict[str, Any]] = []

        # The first word of a sentence is capitalised for grammar, so it
        # is rejected only when it is an ordinary opener (STOPWORDS below).
        # Skipping it outright lost names: "Rahul uses Java."
        for match in _TITLE_PATTERN.finditer(text):
            first, second = match.group(1), match.group(2)
            phrase = f"{first} {second}" if second else first
            lowered = phrase.lower()

            if lowered in known or lowered in STOPWORDS:
                continue
            if any(word in STOPWORDS for word in lowered.split()):
                continue
            if any(lowered in entity["text"] for entity in already):
                continue

            # "Rahul uses Java" / "Amit created Project Beta" -> a person.
            follows = text[match.end():match.end() + 28].lower()
            acts_like_person = bool(
                re.match(
                    r"\s+(?:uses?|used|created|likes?|prefers?|works?|wrote|"
                    r"made|built|said|told|has|have|is using|is learning)\b",
                    follows,
                )
            )

            guesses.append(
                {
                    "name": phrase,
                    "type": PERSON if (second or acts_like_person) else COMPANY,
                    "text": lowered,
                    "context": text.strip()[:200],
                    "guessed": True,
                }
            )
            known.add(lowered)

        return guesses

    # ------------------------------------------------------------------
    def track(self, text: str) -> List[Dict[str, Any]]:
        """Extract entities and update the in-memory registry."""
        found = self.extract(text)
        for entity in found:
            key = f"{entity['type']}:{entity['name'].lower()}"
            record = self.seen.get(key)
            if record:
                record["mentions"] += 1
                record["context"] = entity["context"]
            else:
                self.seen[key] = {**entity, "mentions": 1}
        return found

    def lookup(self, name: str) -> Optional[Dict[str, Any]]:
        target = name.strip().lower()
        for record in self.seen.values():
            if record["name"].lower() == target or record["text"] == target:
                return record
        return None

    def all(self) -> List[Dict[str, Any]]:
        return sorted(
            self.seen.values(), key=lambda r: r["mentions"], reverse=True
        )

    def clear(self) -> None:
        self.seen.clear()


entity_tracker = EntityTracker()

__all__ = [
    "EntityTracker",
    "entity_tracker",
    "PERSON",
    "COMPANY",
    "APP",
    "PLACE",
    "PROJECT",
    "OBJECT",
    "TOPIC",
]
