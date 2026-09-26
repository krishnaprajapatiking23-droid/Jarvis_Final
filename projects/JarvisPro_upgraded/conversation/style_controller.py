"""
==========================================
JARVIS PRO
Style Controller  (variation features 6, 7, 8, 20, 31)
==========================================

Turns a :class:`~conversation.response_planner.ResponsePlan` into the two
things the model actually needs:

  * ``parameters()`` - generation parameters (temperature, top_p,
    repeat_penalty, num_predict, seed) for the local Ollama model.
  * ``directives()`` - short natural-language instructions that tell the
    model how to shape *this* answer: length, structure, knowledge level,
    opening policy, what wording to avoid, which language to reply in.

The variation comes from these two levers, never from a stored list of
alternative answers.  Facts stay with the model; only expression changes.
"""

from __future__ import annotations

import logging
import zlib
from typing import Any, Dict, List, Sequence

log = logging.getLogger("jarvis.conversation.style")

# ------------------------------------------------------------------
# Diversity levels (31).  MEDIUM is the default.
# ------------------------------------------------------------------
DIVERSITY_LEVELS: Dict[str, Dict[str, float]] = {
    "low": {"temperature": 0.35, "top_p": 0.85, "repeat_penalty": 1.05},
    "medium": {"temperature": 0.70, "top_p": 0.92, "repeat_penalty": 1.15},
    "high": {"temperature": 0.92, "top_p": 0.95, "repeat_penalty": 1.25},
}

DEFAULT_LEVEL = "medium"

# Factual questions get near-deterministic settings (29).
FACTUAL_PARAMETERS = {"temperature": 0.15, "top_p": 0.70, "repeat_penalty": 1.0}

# Response length budget in tokens (8).
DEPTH_TOKENS: Dict[str, int] = {
    "one_line": 60,
    "short": 140,
    "normal": 380,
    "deep": 900,
}

DEPTH_DIRECTIVES: Dict[str, str] = {
    "one_line": "Answer in a single sentence. No preamble, no list, no follow-up offer.",
    "short": "Keep it to two or three sentences.",
    "normal": "Give a natural, conversational answer of about three to six sentences.",
    "deep": (
        "Explain thoroughly: cover the how and the why, and include a concrete "
        "example. Use short paragraphs or bullets where they genuinely help."
    ),
}

# Structure variation (7).
STRUCTURES: Dict[str, str] = {
    "A": "Structure: definition first, then a concrete example, then where it is used.",
    "B": "Structure: one-sentence answer first, then the explanation, then an example.",
    "C": "Structure: plain explanation, then why it matters, then an example.",
    "D": "Structure: the direct answer, then the single most important detail.",
    "E": "Structure: a short analogy, then the technical explanation.",
}

# Which structures suit which length.
DEPTH_STRUCTURES: Dict[str, Sequence[str]] = {
    "one_line": ("D",),
    "short": ("D", "B"),
    "normal": ("B", "A", "C", "D", "E"),
    "deep": ("A", "C", "E", "B"),
}

KNOWLEDGE_DIRECTIVES: Dict[str, str] = {
    "beginner": (
        "The user is new to this area. Use plain words, define jargon the "
        "first time and keep the mental model simple."
    ),
    "intermediate": (
        "The user knows the basics. Skip beginner definitions and get to the "
        "useful part."
    ),
    "advanced": (
        "The user is experienced. Be precise and technical, skip introductory "
        "explanations, and do not explain concepts they clearly already use."
    ),
}

OPENING_DIRECTIVES: Dict[str, str] = {
    "none": (
        "Start directly with the answer itself. Do not open with a filler "
        "word or an acknowledgement."
    ),
    "natural": (
        "You may begin with a short natural lead-in such as 'Basically', "
        "'In simple terms', 'The short answer is' or 'Think of it this way' - "
        "but only if it genuinely fits, and never a stock enthusiasm phrase."
    ),
    "direct": "Answer the question first, then add detail if it is needed.",
}

LANGUAGE_DIRECTIVES: Dict[str, str] = {
    "hinglish": (
        "The user wrote in Hinglish. Reply in the same Hinglish style "
        "(Roman-script Hindi mixed with English technical words). Do not "
        "switch to pure English or to Devanagari."
    ),
    "hindi": (
        "The user wrote in Hindi. Reply in Hindi, keeping technical terms in "
        "English where that is normal."
    ),
    "english": "",
}

TONE_DIRECTIVES: Dict[str, str] = {
    "frustrated": (
        "The user sounds frustrated. Acknowledge the problem in at most one "
        "short clause, then go straight to the fix. Do not apologise "
        "repeatedly and do not sound cheerful."
    ),
    "confused": (
        "The user sounds unsure. Re-explain from a different angle instead of "
        "repeating the earlier wording."
    ),
    "excited": (
        "The user is pleased. Match the energy in a few words, then move the "
        "work forward."
    ),
    "tired": "Keep it short and undemanding.",
    "angry": "Stay calm and factual. Fix the problem, do not defend yourself.",
    "sad": "Be warm but brief, then be useful.",
}


def level() -> str:
    """Configured diversity level: low / medium / high (31)."""
    try:
        from conversation.identity import identity

        configured = str(
            identity.settings().get("response_diversity", DEFAULT_LEVEL)
        ).strip().lower()
        if configured in DIVERSITY_LEVELS:
            return configured
    except Exception as error:  # pragma: no cover - defensive
        log.debug("diversity level unreadable: %s", error)
    return DEFAULT_LEVEL


def _seed(*parts: Any) -> int:
    """Stable seed from the given parts (hash() is salted per process)."""
    raw = "|".join(str(part) for part in parts).encode("utf-8", "ignore")
    return int(zlib.crc32(raw) % 1_000_000)


# Round-robin position per depth, used when the caller has no history.
_ROTATION: Dict[str, int] = {}


def structure_for(depth: str, recent: Sequence[str] = ()) -> str:
    """Pick a structure that suits the length and was not just used (7, 19).

    Deliberately *not* random: it walks the ordered list for this depth and
    takes the first option that has not been used recently, so the shape of
    the answer changes between repeats but stays predictable per context.
    """
    options = list(DEPTH_STRUCTURES.get(depth, DEPTH_STRUCTURES["normal"]))
    if not options:
        return "B"
    used = [item for item in recent if item in options]

    if not used:
        # No history to work from: walk the list so a repeated question
        # still changes shape.  Deterministic, never random.
        position = _ROTATION.get(depth, 0) % len(options)
        _ROTATION[depth] = position + 1
        return options[position]

    for option in options:
        if option not in used:
            return option

    # Everything was used: continue the rotation from the oldest one.
    return options[(options.index(used[-1]) + 1) % len(options)]


def parameters(plan: Any, attempt: int = 0) -> Dict[str, Any]:
    """Generation parameters for this plan and retry attempt (20)."""
    depth = getattr(plan, "depth", "normal")
    factual = bool(getattr(plan, "factual", False))
    diversity = getattr(plan, "diversity", "") or level()

    if factual:
        base = dict(FACTUAL_PARAMETERS)
    else:
        base = dict(DIVERSITY_LEVELS.get(diversity, DIVERSITY_LEVELS[DEFAULT_LEVEL]))

    # A repeated question and each retry nudge the sampling a little wider,
    # never past a level that would risk accuracy.
    repeats = int(getattr(plan, "repeat_count", 0) or 0)
    if not factual:
        base["temperature"] = round(
            min(base["temperature"] + (0.06 * repeats) + (0.10 * attempt), 0.95), 3
        )
        base["repeat_penalty"] = round(
            min(base["repeat_penalty"] + (0.05 * attempt), 1.35), 3
        )

    parameters_out: Dict[str, Any] = {
        "temperature": base["temperature"],
        "top_p": base["top_p"],
        "repeat_penalty": base["repeat_penalty"],
        "num_predict": DEPTH_TOKENS.get(depth, DEPTH_TOKENS["normal"]),
    }

    # A fresh seed per (question, repeat, attempt) is what makes the same
    # question sample a different phrasing instead of replaying one.
    if not factual:
        parameters_out["seed"] = _seed(
            getattr(plan, "fingerprint", ""), repeats, attempt
        )

    return parameters_out


def directives(plan: Any, attempt: int = 0) -> List[str]:
    """Instruction lines describing how to shape this specific answer."""
    lines: List[str] = []

    depth = getattr(plan, "depth", "normal")
    lines.append(DEPTH_DIRECTIVES.get(depth, DEPTH_DIRECTIVES["normal"]))

    if bool(getattr(plan, "factual", False)):
        lines.append(
            "This question has one precise answer. State it exactly and stop. "
            "Do not pad it or offer alternatives."
        )
        return lines

    structure = getattr(plan, "structure", "")
    if structure in STRUCTURES:
        lines.append(STRUCTURES[structure])

    knowledge = getattr(plan, "knowledge_level", "intermediate")
    if knowledge in KNOWLEDGE_DIRECTIVES:
        lines.append(KNOWLEDGE_DIRECTIVES[knowledge])

    opening = getattr(plan, "opening_policy", "direct")
    if opening in OPENING_DIRECTIVES:
        lines.append(OPENING_DIRECTIVES[opening])

    avoid_openings = [item for item in getattr(plan, "avoid_openings", []) or [] if item]
    if avoid_openings:
        shown = "; ".join(f'"{item}"' for item in avoid_openings[:3])
        lines.append(
            f"You recently started replies with {shown}. Open this one differently."
        )

    previous = (getattr(plan, "previous_answer", "") or "").strip()
    if previous:
        excerpt = previous[:240].replace("\n", " ")
        lines.append(
            "You have already answered this question before. Your earlier "
            f'answer was: "{excerpt}". Keep every fact identical but say it '
            "in genuinely different words, with a different structure, and "
            "add at least one useful detail you did not mention then. You may "
            "briefly note that you covered this earlier if it reads naturally "
            "- do not force it."
        )

    if bool(getattr(plan, "build_on_previous", False)):
        lines.append(
            "This is a follow-up in an ongoing conversation. Do not restate "
            "what you already explained; answer only the new part and build on "
            "what was said."
        )

    project = (getattr(plan, "project", "") or "").strip()
    if project:
        lines.append(
            f"The user is currently working on {project}. Connect the answer to "
            "that work when it genuinely helps, otherwise ignore it."
        )

    tone = getattr(plan, "tone", "")
    if tone in TONE_DIRECTIVES:
        lines.append(TONE_DIRECTIVES[tone])

    language = getattr(plan, "language", "english")
    language_line = LANGUAGE_DIRECTIVES.get(language, "")
    if language_line:
        lines.append(language_line)

    if bool(getattr(plan, "use_example", False)):
        lines.append("Include one short, concrete example.")

    lines.append(
        "Never open with 'Certainly', 'Absolutely', 'Great question', "
        "'Of course' or 'Sure thing', and never close by offering further "
        "help. Do not invent facts to sound different: wording varies, facts "
        "do not."
    )

    revision = (getattr(plan, "revision", "") or "").strip()
    if revision:
        lines.append(revision)

    if attempt:
        lines.append(
            "Your previous draft was too close to something you already said. "
            "Rewrite it from a different angle - different opening, different "
            "order, different example - with the same facts."
        )

    return [line for line in lines if line]


__all__ = [
    "DIVERSITY_LEVELS",
    "DEPTH_TOKENS",
    "DEPTH_DIRECTIVES",
    "STRUCTURES",
    "KNOWLEDGE_DIRECTIVES",
    "level",
    "structure_for",
    "parameters",
    "directives",
]
