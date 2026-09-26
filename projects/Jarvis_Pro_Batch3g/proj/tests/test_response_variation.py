"""
==========================================
JARVIS PRO
Tests: Human-Like Response & Variation Engine
==========================================

Covers the ten scenarios from the specification plus the guard rails:
cliche / reasoning-trace stripping, bounded retries, factual precision,
minimal acknowledgements and rotating command confirmations.

The model is replaced by a FakeLLM so the tests are deterministic and run
without Ollama.  FakeLLM reads the RESPONSE DIRECTIVES block that the
style controller appends to the prompt, which is how we assert that
length, structure, language and "say it differently" instructions really
reach the AI Brain.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation import question_similarity as qs
from conversation import repetition_detector, response_planner, response_quality
from conversation import store, style_controller
from conversation.response_generator import (
    ResponseGenerator,
    is_repeat_question,
    response_generator,
)
from conversation.response_memory import ResponseMemory, response_memory


# ======================================================================
# helpers
# ======================================================================
class FakeLLM:
    """Deterministic stand-in for Ollama that reacts to the directives."""

    def __init__(self, text="Python is a general-purpose programming language."):
        self.text = text
        self.prompts = []
        self.options = []

    def __call__(self, prompt, options=None):
        self.prompts.append(prompt)
        self.options.append(dict(options or {}))

        attempt = len(self.prompts)
        directives = prompt.split("RESPONSE DIRECTIVES")[-1]

        if "ONE sentence" in directives:
            return "Python is a high-level programming language."

        if "Explain thoroughly" in directives:
            return (
                "Python is a high-level, dynamically typed programming "
                "language. It is used for automation, AI, data analysis and "
                "web development, and its standard library plus package "
                "ecosystem is why teams pick it. For example, a JARVIS-style "
                "assistant can be written entirely in Python, from the voice "
                "pipeline down to the SQLite storage layer, which is the kind "
                "of end-to-end project it suits best."
            )

        if "already answered" in directives or "different words" in directives:
            return (
                f"Variant {attempt}: a versatile language people reach for in "
                "automation and data work."
            )

        return self.text


def fresh_store():
    store.use_database(os.path.join(tempfile.mkdtemp(), "variation.db"))
    store.create_tables()


def reset():
    fresh_store()
    response_memory.clear()
    response_planner.knowledge_tracker.reset()


def last_directives(llm):
    return llm.prompts[-1].split("RESPONSE DIRECTIVES")[-1]


# ======================================================================
# 1. semantic question similarity  (features 2, 3)
# ======================================================================
def test_same_question_recognised():
    assert qs.same_request("What is Python?", "what is python")


def test_reworded_question_recognised():
    for variant in (
        "Can you explain Python?",
        "Tell me about Python.",
        "What exactly is Python?",
        "Can you tell me what Python is?",
    ):
        assert qs.same_request("What is Python?", variant), variant


def test_hinglish_question_recognised():
    assert qs.same_request("What is Python?", "Python kya hai?")


def test_different_facet_is_a_different_request():
    assert not qs.same_request("What is Python?", "What is Python used for?")
    assert not qs.same_request("What is Python?", "Why is Python popular?")


def test_different_subject_is_a_different_request():
    assert not qs.same_request("What is Python?", "What is SQLite?")


def test_fingerprint_is_shared_by_equivalent_questions():
    assert qs.fingerprint("What is Python?") == qs.fingerprint("python kya hai")


def test_is_question_detection():
    assert qs.is_question("What is Python?")
    assert qs.is_question("Python kya hai")
    assert not qs.is_question("Open Chrome")


# ======================================================================
# 2. response memory  (features 4, 18, 28, 33)
# ======================================================================
def test_memory_finds_previous_answer_for_reworded_question():
    memory = ResponseMemory()
    memory._hydrated = True
    memory.record("What is Python?", "Python is a programming language.", "s1")

    previous = memory.previous("Tell me about Python.", "s1")

    assert previous is not None
    assert previous["times_asked"] == 1
    assert previous["same_session"] is True


def test_memory_does_not_match_unrelated_question():
    memory = ResponseMemory()
    memory._hydrated = True
    memory.record("What is Python?", "Python is a language.", "s1")

    assert memory.previous("What is SQLite?", "s1") is None


def test_memory_merges_the_same_turn_instead_of_counting_it_twice():
    memory = ResponseMemory()
    memory._hydrated = True
    memory.record("What is Python?", "Draft answer.", "s1", turn=1)
    memory.record("What is Python?", "Final answer.", "s1", turn=1)

    assert memory.count() == 1
    assert memory.times_asked("What is Python?") == 1


def test_memory_tracks_openings_and_structures():
    memory = ResponseMemory()
    memory._hydrated = True
    memory.record("What is Python?", "Basically it is a language.", "s1", structure="B")

    assert memory.recent_openings() == ["basically it is a"]
    assert memory.recent_structures() == ["B"]


def test_repeat_question_helper():
    reset()
    assert not is_repeat_question("What is Python?", "s1")

    response_memory.record("What is Python?", "Python is a language.", "s1")

    assert is_repeat_question("Python kya hai?", "s1")


# ======================================================================
# 3. repetition detection and cliche removal  (features 5, 15, 18)
# ======================================================================
def test_identical_answers_are_flagged_as_repetitive():
    answer = "Python is a programming language used for automation and AI."
    report = repetition_detector.check(answer, recent_answers=[answer])

    assert report["repetitive"] is True
    assert report["score"] > 0.9


def test_different_answers_are_not_flagged():
    report = repetition_detector.check(
        "It is popular because the syntax is small and the ecosystem is huge.",
        recent_answers=["Python is a programming language used for automation."],
    )

    assert report["repetitive"] is False


def test_cliches_are_stripped():
    cleaned = repetition_detector.strip_cliches(
        "Certainly! Python is a language. Hope this helps!"
    )

    assert cleaned == "Python is a language."


def test_reasoning_traces_are_stripped():
    cleaned = repetition_detector.strip_cliches(
        "<think>the user wants a definition</think>Python is a language."
    )

    assert "think" not in cleaned.lower()
    assert cleaned == "Python is a language."


def test_reused_opening_is_detected():
    report = repetition_detector.check(
        "Basically it is a language for automation.",
        recent_openings=["basically it is a"],
    )

    assert report["reused_opening"] is True


# ======================================================================
# 4. planner decisions  (features 8, 9, 23, 24, 26, 29, 30, 32)
# ======================================================================
def test_depth_from_user_cues():
    assert response_planner.detect_depth("Explain Python in one line") == "one_line"
    assert response_planner.detect_depth("What is Python? quickly") == "short"
    assert response_planner.detect_depth("Explain Python deeply") == "deep"
    assert response_planner.detect_depth("What is Python?") == "normal"


def test_language_detection():
    assert response_planner.detect_language("Python kya hai?") == "hinglish"
    assert response_planner.detect_language("What is Python?") == "english"


def test_factual_questions_detected():
    assert response_planner.detect_factual("What is 2 + 2?")
    assert not response_planner.detect_factual("What is Python?")


def test_minimal_turn_detection():
    assert response_planner.detect_minimal("Okay.") == "ack"
    assert response_planner.detect_minimal("Thanks.") == "thanks"
    assert response_planner.detect_minimal("Nice") == "praise"
    assert response_planner.detect_minimal("What is Python?") == ""


def test_plan_marks_command_turns():
    reset()
    plan = response_planner.plan("Open Chrome", action="automation")

    assert plan.kind == "command"
    assert plan.max_retries == 0


def test_plan_uses_knowledge_signals():
    reset()
    response_planner.knowledge_tracker.observe("s-know", "I'm learning programming")
    plan = response_planner.plan("What is Python?", session_id="s-know")

    assert plan.knowledge_level == "beginner"

    response_planner.knowledge_tracker.reset("s-adv")
    response_planner.knowledge_tracker.observe(
        "s-adv", "I'm building an AI system with async threading"
    )
    advanced = response_planner.plan("What is Python?", session_id="s-adv")

    assert advanced.knowledge_level == "advanced"


def test_plan_records_previous_answer_for_repeat():
    reset()
    response_memory.record("What is Python?", "Python is a language.", "s1")

    plan = response_planner.plan("What is Python?", session_id="s1", turn=3)

    assert plan.repeat_count == 1
    assert plan.previous_answer == "Python is a language."
    assert plan.reference_previous is True


# ======================================================================
# 5. style controller  (features 7, 19, 20, 31)
# ======================================================================
def test_parameters_scale_with_repeats_but_stay_bounded():
    reset()
    plan = response_planner.plan("What is Python?", session_id="s1")
    first = style_controller.parameters(plan, 0)

    plan.repeat_count = 3
    repeated = style_controller.parameters(plan, 1)

    assert repeated["temperature"] > first["temperature"]
    assert repeated["temperature"] <= 0.95
    assert repeated["repeat_penalty"] <= 1.35


def test_factual_parameters_are_precise():
    plan = response_planner.plan("What is 2 + 2?")
    options = style_controller.parameters(plan)

    assert options["temperature"] <= 0.2
    assert "seed" not in options


def test_seed_changes_between_attempts():
    reset()
    plan = response_planner.plan("What is Python?", session_id="s1")

    assert (
        style_controller.parameters(plan, 0)["seed"]
        != style_controller.parameters(plan, 1)["seed"]
    )


def test_structure_rotates_away_from_recent_ones():
    first = style_controller.structure_for("normal", [])
    second = style_controller.structure_for("normal", [first])

    assert first != second


def test_diversity_level_defaults_to_medium():
    assert style_controller.level() in style_controller.DIVERSITY_LEVELS


# ======================================================================
# 6. quality gate  (features 16, 17, 27)
# ======================================================================
def test_quality_flags_repetition():
    reset()
    plan = response_planner.plan("What is Python?", session_id="s1")
    answer = "Python is a programming language used for automation and AI."

    report = response_quality.check(answer, plan, recent_answers=[answer])

    assert report.ok is False
    assert "repeats_recent" in report.issues
    assert report.directive


def test_quality_flags_one_line_overflow():
    reset()
    plan = response_planner.plan("Explain Python in one line", session_id="s1")
    report = response_quality.check("word " * 200, plan)

    assert "too_long" in report.issues


def test_quality_passes_provider_status_messages():
    reset()
    plan = response_planner.plan("What is Python?", session_id="s1")
    report = response_quality.check("Ollama is offline.", plan)

    assert report.unavailable is True
    assert report.ok is True


# ======================================================================
# 7. SPEC TEST 1 - same question asked repeatedly
# ======================================================================
def test_spec_1_same_question_many_times():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    replies = [
        generator.generate(
            "What is Python?",
            ask=llm,
            base_prompt="BASE",
            session_id="s1",
            turn=index + 1,
        )
        for index in range(6)
    ]

    assert all(replies)
    assert len(set(replies)) > 1
    assert "already answered this question before" in llm.prompts[-1]
    assert llm.options[-1]["temperature"] <= 0.95


def test_spec_1_facts_are_not_invented_by_the_layer():
    reset()
    llm = FakeLLM("Python was created by Guido van Rossum.")
    generator = ResponseGenerator()

    reply = generator.generate(
        "Who created Python?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    assert reply == "Python was created by Guido van Rossum."


# ======================================================================
# 8. SPEC TEST 2 - same meaning, different wording
# ======================================================================
def test_spec_2_same_meaning_different_wording():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    for index, variant in enumerate(
        ("Can you explain Python?", "Tell me about Python.", "Python kya hai?"),
        start=2,
    ):
        generator.generate(
            variant, ask=llm, base_prompt="BASE", session_id="s1", turn=index
        )

        assert generator.last_plan.repeat_count >= 1, variant
        assert "already answered this question before" in llm.prompts[-1], variant

    assert "Hinglish" in last_directives(llm)


# ======================================================================
# 9. SPEC TEST 3 - follow-up chain
# ======================================================================
class _Understanding:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def test_spec_3_followup_builds_on_previous_answer():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    understanding = _Understanding(
        intent="question",
        topic="Python",
        entities=[],
        references=[{"text": "it"}],
        emotion="neutral",
        style="balanced",
        session_id="s1",
        turn=2,
    )

    generator.generate(
        "Why is it popular?",
        ask=llm,
        base_prompt="BASE",
        understanding=understanding,
        session_id="s1",
        turn=2,
    )

    assert generator.last_plan.build_on_previous is True
    assert "follow-up" in last_directives(llm)


# ======================================================================
# 10. SPEC TEST 4 - repeated question in a new session
# ======================================================================
def test_spec_4_repeat_across_sessions_is_not_replayed():
    reset()
    llm = FakeLLM("SQLite is a lightweight embedded database.")
    generator = ResponseGenerator()

    first = generator.generate(
        "What is SQLite?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    second = generator.generate(
        "What is SQLite?", ask=llm, base_prompt="BASE", session_id="s2", turn=1
    )

    assert generator.last_plan.repeat_count == 1
    assert generator.last_plan.same_session is False
    assert generator.last_plan.reference_previous is False
    assert second != first


# ======================================================================
# 11. SPEC TESTS 5-7 - knowledge level and length
# ======================================================================
def test_spec_5_beginner_and_advanced_directives_differ():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    response_planner.knowledge_tracker.observe("s-b", "I'm learning programming")
    generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s-b", turn=2
    )
    beginner = last_directives(llm)

    response_planner.knowledge_tracker.observe(
        "s-a", "I'm building an AI system with async threading"
    )
    generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s-a", turn=2
    )
    advanced = last_directives(llm)

    assert "new to this area" in beginner
    assert "experienced" in advanced


def test_spec_6_one_line_request():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    reply = generator.generate(
        "Explain Python in one line.",
        ask=llm,
        base_prompt="BASE",
        session_id="s1",
        turn=1,
    )

    assert generator.last_plan.depth == "one_line"
    assert reply.count(".") == 1
    assert llm.options[-1]["num_predict"] == style_controller.DEPTH_TOKENS["one_line"]


def test_spec_7_deep_request():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    reply = generator.generate(
        "Explain Python deeply.", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    assert generator.last_plan.depth == "deep"
    assert len(reply) > 200
    assert llm.options[-1]["num_predict"] == style_controller.DEPTH_TOKENS["deep"]


# ======================================================================
# 12. SPEC TEST 8/9 - commands and corrections
# ======================================================================
def test_spec_8_command_acknowledgement_rotates():
    generator = ResponseGenerator()

    lines = [generator.acknowledge("open", "Chrome") for _ in range(3)]

    assert len(set(lines)) == 3
    assert all("Chrome" in line for line in lines)


def test_spec_9_correction_target_is_respected():
    generator = ResponseGenerator()

    first = generator.acknowledge("open", "Chrome")
    corrected = generator.acknowledge("open", "Edge")

    assert "Chrome" in first
    assert "Edge" in corrected
    assert "Chrome" not in corrected


def test_command_failure_is_reported_honestly():
    generator = ResponseGenerator()

    reply = generator.acknowledge("open", "Chrome", success=False)

    assert "Chrome" in reply
    assert "fail" in reply.lower()


def test_command_plan_skips_retries_and_openings():
    reset()
    plan = response_planner.plan("Open Chrome", action="browser")

    assert plan.opening_policy == "none"
    assert plan.depth == "short"


# ======================================================================
# 13. SPEC TEST 10 - topic change
# ======================================================================
def test_spec_10_topic_change_is_a_new_request():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    generator.generate(
        "Tell me about Python.", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    generator.generate(
        "By the way, what's the weather?",
        ask=llm,
        base_prompt="BASE",
        session_id="s1",
        turn=2,
    )

    assert generator.last_plan.repeat_count == 0
    assert "already answered this question before" not in llm.prompts[-1]


# ======================================================================
# 14. minimal turns, factual precision, retry cap
# ======================================================================
def test_minimal_turn_never_calls_the_model():
    reset()
    llm = FakeLLM()
    generator = ResponseGenerator()

    reply = generator.generate("Okay.", ask=llm, base_prompt="BASE", session_id="s1")

    assert llm.prompts == []
    assert len(reply) < 20


def test_thanks_gets_a_short_reply():
    reset()
    generator = ResponseGenerator()

    reply = generator.generate("Thanks.", ask=FakeLLM(), session_id="s1")

    assert reply in ("Anytime.", "Sure.", "No problem.", "Happy to.")


def test_factual_answer_is_not_varied():
    reset()
    llm = FakeLLM("4.")
    generator = ResponseGenerator()

    first = generator.generate(
        "What is 2 + 2?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )
    second = generator.generate(
        "What is 2 + 2?", ask=llm, base_prompt="BASE", session_id="s1", turn=2
    )

    assert first == second == "4."
    assert generator.last_plan.factual is True
    assert generator.attempts == 1


def test_retries_are_capped():
    reset()
    repeated = "Python is a programming language used for automation and AI."
    response_memory.record("What is Python?", repeated, "s1")

    class Stubborn(FakeLLM):
        def __call__(self, prompt, options=None):
            self.prompts.append(prompt)
            self.options.append(dict(options or {}))
            return repeated

    llm = Stubborn()
    generator = ResponseGenerator()

    reply = generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s1", turn=2
    )

    assert len(llm.prompts) <= response_quality.MAX_RETRIES + 1
    assert reply == repeated


def test_generator_works_with_single_argument_brain():
    reset()

    def simple(prompt):
        return "Python is a language."

    generator = ResponseGenerator()
    reply = generator.generate(
        "What is Python?", ask=simple, base_prompt="BASE", session_id="s1", turn=1
    )

    assert reply == "Python is a language."


def test_model_failure_degrades_quietly():
    reset()

    def broken(prompt, options=None):
        raise RuntimeError("model down")

    generator = ResponseGenerator()

    assert generator.generate(
        "What is Python?", ask=broken, base_prompt="BASE", session_id="s1", turn=1
    ) == ""


def test_offline_message_is_not_recorded_as_an_answer():
    reset()
    llm = FakeLLM("Ollama is offline.")
    generator = ResponseGenerator()

    generator.generate(
        "What is Python?", ask=llm, base_prompt="BASE", session_id="s1", turn=1
    )

    assert response_memory.count() == 0


# ======================================================================
# 15. integration with the live pipeline modules
# ======================================================================
def test_reply_controller_adds_no_fixed_decoration():
    from brains_v2.controllers.reply_controller import reply_controller

    reply = reply_controller.process(
        {"type": "chat"}, None, "Certainly! Python is a language. Hope this helps!"
    )

    assert reply == "Python is a language."


def test_style_engine_no_longer_prefixes_replies():
    from brains_v2.style import style

    style.update({"mode": "professional"})

    assert style.apply("Python is a language.") == "Python is a language."


def test_action_reply_uses_rotating_acknowledgement():
    from brains_v2.response import generate

    replies = {generate({"status": "opened", "app": "chrome"}) for _ in range(3)}

    assert len(replies) >= 2
    assert all("Chrome" in reply or "Done" in reply for reply in replies)


def test_already_open_status_is_stable():
    from brains_v2.response import generate

    assert generate({"status": "already_open", "app": "chrome"}) == (
        "Chrome is already open."
    )


def test_prompt_builder_always_includes_the_user_message():
    from brains_v2.llm.prompt_builder import build

    prompt = build("What is Python?", None, "CONTEXT BLOCK")

    assert "CONTEXT BLOCK" in prompt
    assert "What is Python?" in prompt


def test_conversation_engine_records_response_memory():
    reset()
    from conversation.conversation_engine import ConversationEngine

    engine = ConversationEngine(mode="text")
    understanding = engine.understand("What is Python?")
    engine.commit(understanding, "Python is a general-purpose language.")

    assert response_memory.count() >= 1
    assert response_memory.previous("Python kya hai?") is not None


def test_engine_repeat_then_variation_directive():
    reset()
    from conversation.conversation_engine import ConversationEngine

    engine = ConversationEngine(mode="text")
    first = engine.understand("What is Python?")
    engine.commit(first, "Python is a general-purpose language.")

    llm = FakeLLM()
    second = engine.understand("What is Python?")
    reply = response_generator.generate(
        second.text,
        ask=llm,
        base_prompt=engine.prompt(second),
        understanding=second,
        session_id=second.session_id,
        turn=second.turn,
    )

    assert reply
    assert "already answered this question before" in llm.prompts[-1]
