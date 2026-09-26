"""
==========================================
JARVIS PRO
Same-answer bug reproduction harness
==========================================

Proves the bug and the repair with numbers instead of opinions.

The model is replaced by a *deterministic stand-in*: it returns one
phrasing per distinct (prompt, sampling-options) pair, which is exactly
how a real LLM behaves when it is called with the same prompt and no
sampling parameters.  Nothing about the JARVIS pipeline is faked.

    OLD PATH  ->  same prompt, no options        -> same answer every time
    NEW PATH  ->  planner + directives + options -> naturally different

Run it:

    python tools\\repro_same_answer.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from conversation import store  # noqa: E402


# One paraphrase per distinct model input.  Facts identical, wording not.
PHRASINGS = (
    "Python is a high-level programming language used for AI and automation.",
    "Python is a general-purpose language known for readable syntax, and it "
    "is widely used in AI, automation and data work.",
    "Think of Python as the glue language: simple syntax, huge library set, "
    "and it runs everything from scripts to machine-learning pipelines.",
    "Python is an interpreted, dynamically typed language. Its appeal is "
    "readability, which is why data science and automation adopted it.",
    "In short: a programming language built for clarity, popular in AI, "
    "backend services, automation and analysis.",
    "Python is a programming language designed around readable code, used "
    "heavily for scripting, AI work and data pipelines.",
)


class DeterministicModel:
    """Same input -> same output. Different input -> different output."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, prompt: str, options=None) -> str:
        self.calls += 1
        key = repr(prompt) + repr(sorted((options or {}).items()))
        index = zlib.crc32(key.encode("utf-8", "ignore")) % len(PHRASINGS)
        return PHRASINGS[index]


def old_path(question: str, times: int) -> list:
    """The pre-fix behaviour: fixed prompt, no generation parameters."""
    model = DeterministicModel()
    prompt = (
        "You are JARVIS, a helpful assistant.\n"
        "Owner: Krishna\n"
        f"User: {question}\nJARVIS:"
    )
    return [model(prompt) for _ in range(times)]


def new_path(question: str, times: int) -> list:
    """The repaired pipeline: planner + directives + sampling per turn."""
    from conversation.conversation_engine import ConversationEngine
    from conversation.response_generator import response_generator
    from conversation.response_memory import response_memory

    response_memory.clear()
    model = DeterministicModel()
    engine = ConversationEngine(mode="text")

    answers = []
    for _ in range(times):
        understanding = engine.understand(question)
        base_prompt = getattr(understanding, "prompt", "") or (
            "You are JARVIS, a helpful assistant.\n"
            f"User: {question}\nJARVIS:"
        )
        reply = response_generator.generate(
            question,
            ask=model,
            base_prompt=base_prompt,
            understanding=understanding,
            session_id=getattr(understanding, "session_id", ""),
            turn=getattr(understanding, "turn", 0),
        )
        engine.commit(understanding, reply)
        answers.append(reply)
    return answers


def show(title: str, answers: list) -> None:
    from conversation import repetition_detector

    print()
    print(title)
    print("-" * len(title))
    for index, answer in enumerate(answers, start=1):
        print(f"Response {index}: {answer}")

    distinct = list(dict.fromkeys(answers))
    highest = 0.0
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            highest = max(
                highest, repetition_detector.similarity(distinct[i], distinct[j])
            )

    print()
    print(f"unique responses : {len(distinct)} of {len(answers)}")
    if len(distinct) > 1:
        print(f"highest similarity between distinct responses : {highest:.2f}")
    if len(distinct) < len(answers) > 1:
        print(
            "note: the stand-in model only holds "
            f"{len(PHRASINGS)} phrasings, so exact repeats here are a limit "
            "of the harness, not of the pipeline - a real model generates a "
            "new wording per call."
        )


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "What is Python?"
    times = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    store.use_database(os.path.join(tempfile.mkdtemp(), "repro.db"))
    store.create_tables()

    print(f'Question asked {times} times: "{question}"')
    show("BEFORE THE FIX (fixed prompt, no sampling options)", old_path(question, times))
    show("AFTER THE FIX (planned prompt + per-turn sampling)", new_path(question, times))
    print()
    print("Facts stay the same in every answer; only the expression moves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
