"""
==========================================
JARVIS PRO
Manual checker: response variation
==========================================

Runs the real conversation pipeline (Conversation Engine + Human-Like
Response Controller + your AI Brain) and reports whether the same
question produces different wording.

Usage from the project folder:

    python tools\\try_variation.py                     # full scripted check
    python tools\\try_variation.py "What is Python?" 8 # ask one question 8 times
    python tools\\try_variation.py --chat             # free typing session

Nothing here is a unit test - it talks to your actual model (Ollama) if
it is running.  If Ollama is offline the script says so and stops,
because variation cannot be judged without real answers.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation import repetition_detector
from conversation.conversation_engine import ConversationEngine
from conversation.response_generator import response_generator

LINE = "=" * 68


# ----------------------------------------------------------------------
def brain():
    """Return a callable that asks the real model, or None if offline."""
    provider = None

    try:
        from brains_v2.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
    except Exception as error:  # pragma: no cover - environment dependent
        print(f"Ollama provider unavailable ({error}); trying the base provider.")

        try:
            from brains_v2.llm.provider import llm

            provider = llm
        except Exception as fallback_error:
            print(f"No LLM provider could be loaded: {fallback_error}")
            return None

    try:
        online = provider.available()
    except Exception:
        online = False

    if not online:
        print("Ollama is not responding.  Start it first:\n")
        print("    ollama serve")
        print("    ollama run qwen3:4b\n")
        return None

    def ask(prompt, options=None):
        try:
            return provider.generate(prompt, options)
        except TypeError:
            # Stale provider copy that predates generation options.
            print(
                "note: this provider ignores generation options - "
                "your project folder still has an old "
                "brains_v2/llm/ollama_provider.py"
            )
            return provider.generate(prompt)

    return ask


def make_turn(engine, ask):
    def turn(message):
        understanding = engine.understand(message)

        if understanding.handled:
            reply = understanding.handled_reply
        else:
            reply = response_generator.generate(
                understanding.text,
                ask=ask,
                base_prompt=engine.prompt(understanding),
                understanding=understanding,
                session_id=understanding.session_id,
                turn=understanding.turn,
            )

        engine.commit(understanding, reply)
        return reply

    return turn


def report(answers):
    """Print how different the answers actually were."""
    print("\n" + LINE)
    print(f"unique answers : {len(set(answers))} of {len(answers)}")

    worst = 0.0
    for index in range(1, len(answers)):
        for earlier in answers[:index]:
            worst = max(worst, repetition_detector.similarity(answers[index], earlier))

    print(f"highest similarity between any two answers : {worst:.2f}")
    print("(below 0.82 means the variation layer is doing its job)")

    openings = [repetition_detector.opening_of(text) for text in answers]
    print(f"unique openings : {len(set(openings))} of {len(openings)}")
    print(LINE)


# ----------------------------------------------------------------------
def repeat_check(turn, question, times):
    print(f"\n{LINE}\nAsking the same question {times} times\n{LINE}")

    answers = []
    for index in range(times):
        reply = turn(question)
        answers.append(reply)
        print(f"\n[{index + 1}] {question}")
        print(f"    {reply}")

    report(answers)
    return answers


def scripted_check(turn):
    scenarios = [
        ("Same meaning, different wording", [
            "What is Python?",
            "Can you explain Python?",
            "Tell me about Python.",
            "Python kya hai?",
        ]),
        ("Follow-up chain", [
            "What is Python?",
            "Why is it popular?",
            "What can I build with it?",
        ]),
        ("Length control", [
            "Explain Python in one line.",
            "Explain Python deeply.",
        ]),
        ("Project-aware context", [
            "I am building JARVIS in Python.",
            "What is SQLite?",
        ]),
        ("Minimal turns", [
            "Okay.",
            "Thanks.",
        ]),
        ("Commands and correction", [
            "Open Chrome.",
            "No, I meant Edge.",
        ]),
        ("Topic change", [
            "Tell me about Python.",
            "By the way, what is the weather?",
        ]),
    ]

    for title, messages in scenarios:
        print(f"\n{LINE}\n{title}\n{LINE}")
        for message in messages:
            reply = turn(message)
            print(f"\nYou    : {message}")
            print(f"JARVIS : {reply}")
            plan = response_generator.last_plan
            if plan is not None:
                print(
                    "         [depth={0} language={1} structure={2} "
                    "asked_before={3} attempts={4}]".format(
                        plan.depth,
                        plan.language,
                        plan.structure,
                        plan.repeat_count,
                        response_generator.attempts,
                    )
                )


def chat(turn):
    print(f"\n{LINE}\nFree chat - type 'exit' to stop\n{LINE}")

    while True:
        try:
            message = input("\nYou    : ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if message.lower() in {"exit", "quit", "bye"}:
            break

        if not message:
            continue

        print(f"JARVIS : {turn(message)}")


# ----------------------------------------------------------------------
def main():
    ask = brain()
    if ask is None:
        return 1

    engine = ConversationEngine(mode="text")
    turn = make_turn(engine, ask)

    arguments = sys.argv[1:]

    if arguments and arguments[0] in {"--chat", "-c"}:
        chat(turn)
    elif arguments:
        question = arguments[0]
        times = int(arguments[1]) if len(arguments) > 1 else 5
        repeat_check(turn, question, times)
    else:
        repeat_check(turn, "What is Python?", 5)
        scripted_check(turn)

    engine.end()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
