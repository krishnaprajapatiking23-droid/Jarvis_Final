"""
==========================================
JARVIS PRO
Feature tests - batch 2
==========================================

Covers the modules added in the second integration batch: event bus, context
engine, experience store, knowledge base, behaviour learning, habits, mistake
journal, personality modes, self-improvement, workflow engine, analytics and
the intelligence loop.

Run it directly (pytest is not installed everywhere):

    python3 tests/test_jarvis_pro_features_v2.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("JARVIS_DEBUG", "0")


# ---------------------------------------------------------------- event bus


def test_event_bus_publish_and_subscribe() -> None:
    from core.event_bus import EventBus

    bus = EventBus()
    seen: list[dict] = []

    bus.subscribe("task.done", lambda payload: seen.append(payload))
    delivered = bus.publish("task.done", {"id": 1})

    assert delivered["delivered"] == 1, delivered
    assert delivered["failed"] == 0, delivered
    assert seen == [{"id": 1}], seen


def test_event_bus_wildcard_and_once() -> None:
    from core.event_bus import EventBus

    bus = EventBus()
    wild: list[str] = []
    single: list[str] = []

    bus.subscribe("task.*", lambda payload: wild.append("wild"))
    bus.once("task.done", lambda payload: single.append("once"))

    bus.publish("task.done", {})
    bus.publish("task.failed", {})

    assert len(wild) == 2, wild
    assert len(single) == 1, single


def test_event_bus_isolates_failing_handler() -> None:
    from core.event_bus import EventBus

    bus = EventBus()
    good: list[int] = []

    def broken(payload: dict) -> None:
        raise RuntimeError("handler exploded")

    bus.subscribe("ping", broken)
    bus.subscribe("ping", lambda payload: good.append(1))

    report = bus.publish("ping", {})

    assert good == [1], "a broken handler must not stop the others"
    assert report["failed"] == 1, report


def test_event_bus_history_and_unsubscribe() -> None:
    from core.event_bus import EventBus

    bus = EventBus()
    listener_id = bus.subscribe("a.b", lambda payload: None)

    bus.publish("a.b", {"n": 1})

    assert bus.unsubscribe(listener_id) is True
    assert bus.publish("a.b", {"n": 2})["delivered"] == 0
    assert len(bus.history()) == 2, bus.history()


# ------------------------------------------------------------ context engine


def test_context_engine_assembles_text() -> None:
    from core.context_engine import ContextEngine

    engine = ContextEngine()
    engine.remember("goal", "finish the JARVIS upgrade", kind="goal")

    assembled = engine.assemble("what is my goal")

    assert isinstance(assembled, str) and assembled.strip(), assembled
    assert "JARVIS upgrade" in assembled, assembled


def test_context_engine_ranks_relevant_items_first() -> None:
    from core.context_engine import ContextEngine

    engine = ContextEngine()
    engine.remember("printer", "the printer is in the study room")
    engine.remember("editor", "my favourite editor is vs code")

    ranked = engine.rank("where is the printer")

    assert ranked, "ranking returned nothing"
    assert "printer" in ranked[0].value.lower(), [item.value for item in ranked]


def test_context_engine_respects_budget() -> None:
    from core.context_engine import ContextEngine

    engine = ContextEngine()

    for index in range(40):
        engine.remember(f"fact{index}", f"fact number {index} " + "padding " * 30)

    assembled = engine.assemble("fact", budget=400)

    assert len(assembled) <= 700, len(assembled)


def test_context_engine_forget_and_expire() -> None:
    from core.context_engine import ContextEngine

    engine = ContextEngine()
    engine.remember("temporary", "temporary detail", ttl=0.01)
    engine.remember("permanent", "permanent detail")

    time.sleep(0.05)
    engine.expire()
    values = [item.value for item in engine.rank()]

    assert "temporary detail" not in values, values
    assert engine.forget("permanent") is True


def test_context_engine_providers_run() -> None:
    from core.context_engine import context_engine

    assert context_engine.collect() >= 0

    snapshot = context_engine.snapshot()

    assert isinstance(snapshot, list), snapshot
    assert context_engine.status()["kinds_supported"], "no context kinds"


# -------------------------------------------------------- experience store


def test_experience_records_and_reports() -> None:
    from memory.experience import experience

    experience.record(
        "unit test goal alpha",
        success=True,
        steps=2,
        duration=1.5,
        strategy="unit",
    )
    experience.record(
        "unit test goal alpha",
        success=False,
        steps=3,
        duration=2.0,
        strategy="unit",
        error="unit failure",
    )

    stats = experience.stats("unit test goal alpha")

    assert stats["attempts"] >= 2, stats
    assert 0 <= stats["success_rate"] <= 100, stats


def test_experience_similar_and_advice() -> None:
    from memory.experience import experience

    experience.record(
        "unit test goal beta", success=True, steps=1, strategy="direct"
    )

    assert isinstance(experience.similar("unit test goal beta"), list)
    assert isinstance(experience.advice("unit test goal beta"), str)


def test_experience_best_strategy() -> None:
    from memory.experience import experience

    for _ in range(3):
        experience.record(
            "unit test goal gamma", success=True, steps=1, strategy="winner"
        )

    experience.record(
        "unit test goal gamma", success=False, steps=1, strategy="loser"
    )

    assert experience.best_strategy("unit test goal gamma") == "winner"


# --------------------------------------------------------- knowledge base


def test_knowledge_learns_and_searches() -> None:
    from memory.knowledge_base import knowledge

    knowledge.learn(
        "The JARVIS event bus lives in core/event_bus.py",
        source="user",
        topic="architecture",
    )

    found = knowledge.search("event bus")

    assert found, "knowledge search found nothing"
    assert any("event bus" in item["fact"].lower() for item in found), found


def test_knowledge_deduplicates() -> None:
    from memory.knowledge_base import knowledge

    fact = "Duplicate unit test fact about JARVIS"

    first = knowledge.learn(fact, source="user", topic="unit")
    second = knowledge.learn(fact, source="user", topic="unit")

    assert first["ok"], first
    assert second["new"] is False, second


def test_knowledge_brief_and_topics() -> None:
    from memory.knowledge_base import knowledge

    knowledge.learn(
        "Unit topic fact for briefing", source="user", topic="unittopic"
    )

    assert isinstance(knowledge.brief("briefing"), str)
    assert "unittopic" in knowledge.topics(), knowledge.topics()


# ------------------------------------------------------ behaviour & habits


def test_behaviour_finds_patterns() -> None:
    from learning.behaviour import behaviour
    from memory.experience import experience

    for _ in range(4):
        experience.record(
            "check the system status", success=True, steps=1, strategy="tool"
        )

    patterns = behaviour.patterns()

    assert isinstance(patterns, list), patterns
    assert any("system" in item["pattern"] for item in patterns), patterns


def test_behaviour_weak_spots_and_summary() -> None:
    from learning.behaviour import behaviour
    from memory.experience import experience

    for _ in range(3):
        experience.record(
            "open the broken app",
            success=False,
            steps=1,
            strategy="tool",
            error="FileNotFoundError",
        )

    assert isinstance(behaviour.weak_spots(), list)
    assert behaviour.summary().strip(), "summary was empty"
    assert isinstance(behaviour.routine(), dict)


def test_habits_produce_suggestions() -> None:
    from learning.habits import habits

    assert isinstance(habits.suggestions(), list)
    assert isinstance(habits.greeting_hint(), str)
    assert isinstance(habits.most_common(), list)


# --------------------------------------------------------- mistake journal


def test_mistakes_record_and_repeat_detection() -> None:
    from learning.mistakes import mistakes

    first = mistakes.record("open notepad", "FileNotFoundError: notepad.exe")
    second = mistakes.record("open notepad", "FileNotFoundError: notepad.exe")

    assert first["ok"], first
    assert second.get("repeat") is True, second
    assert mistakes.seen_before("FileNotFoundError: notepad.exe") is True


def test_mistakes_resolve_and_advise() -> None:
    from learning.mistakes import mistakes

    mistakes.record("launch editor", "PermissionError: access denied")

    assert mistakes.resolve(
        "PermissionError: access denied", "run it as administrator"
    )
    assert "administrator" in mistakes.known_fix(
        "PermissionError: access denied"
    )
    assert "administrator" in mistakes.advice("PermissionError: access denied")


def test_mistakes_signature_groups_similar_errors() -> None:
    from learning.mistakes import mistakes

    one = mistakes.signature("TimeoutError after 30 seconds")
    two = mistakes.signature("TimeoutError after 90 seconds")

    assert one == two, (one, two)


# ------------------------------------------------------------- personality


def test_personality_switches_mode() -> None:
    from personality.modes import personality

    outcome = personality.set_mode("teacher")

    assert outcome["ok"], outcome
    assert personality.mode == "teacher"
    assert "beginner" in personality.system_prompt().lower()


def test_personality_rejects_unknown_mode() -> None:
    from personality.modes import personality

    outcome = personality.set_mode("grumpy")

    assert outcome["ok"] is False, outcome
    assert "available" in outcome, outcome


def test_personality_language_modes() -> None:
    from personality.modes import personality

    assert personality.set_language("hinglish")["ok"]
    assert "Hinglish" in personality.system_prompt()

    assert personality.set_language("hindi")["ok"]
    assert "Devanagari" in personality.system_prompt()

    personality.set_language("english")


def test_personality_detects_spoken_request() -> None:
    from personality.modes import personality

    applied = personality.apply_request(
        "talk to me in developer mode in english"
    )

    assert applied["ok"], applied
    assert personality.mode == "developer"
    assert personality.language == "en"

    personality.set_mode("friendly")


def test_personality_all_modes_have_prompts() -> None:
    from personality.modes import LANGUAGES, MODES

    assert len(MODES) >= 8, list(MODES)
    assert len(LANGUAGES) >= 3, list(LANGUAGES)

    for name, data in MODES.items():
        assert data["prompt"].strip(), name


# -------------------------------------------------------- self-improvement


def test_self_improvement_review_is_safe() -> None:
    from core.self_improvement import self_improvement

    review = self_improvement.review()

    assert review["ok"], review
    assert isinstance(review["proposals"], list), review


def test_self_improvement_dry_run_changes_nothing() -> None:
    from config import config
    from core.self_improvement import self_improvement

    before = config.get("agent.max_retries")
    outcome = self_improvement.improve(dry_run=True)

    assert outcome["ok"], outcome
    assert outcome["applied"] == [], outcome
    assert config.get("agent.max_retries") == before


def test_self_improvement_keeps_settings_within_limits() -> None:
    from core.self_improvement import TUNABLE, self_improvement

    clamped = self_improvement._within_limits("agent.max_retries", 99)

    assert clamped == TUNABLE["agent.max_retries"]["max"], clamped
    assert self_improvement._within_limits("not.a.setting", 1) is None


# ------------------------------------------------------------- workflows


def test_workflow_create_and_describe() -> None:
    from core.workflow_engine import workflows

    created = workflows.create(
        "unit test routine",
        [{"tool": "system_status", "arguments": {}}, "summarise the result"],
        description="unit test workflow",
    )

    assert created["ok"], created
    assert created["steps"] == 2, created
    assert workflows.has("unit test routine")
    assert "unit test routine" in workflows.describe("unit test routine")


def test_workflow_rejects_empty_steps() -> None:
    from core.workflow_engine import workflows

    assert workflows.create("empty routine", [])["ok"] is False
    assert workflows.create("", [{"tool": "system_status"}])["ok"] is False


def test_workflow_runs_steps() -> None:
    from core.workflow_engine import workflows

    workflows.create(
        "unit run routine", [{"tool": "system_status", "arguments": {}}]
    )
    result = workflows.run("unit run routine")

    assert result["total"] == 1, result
    assert isinstance(result["steps"], list) and result["steps"], result
    assert "message" in result, result


def test_workflow_delete_and_unknown_run() -> None:
    from core.workflow_engine import workflows

    workflows.create("throwaway routine", [{"tool": "system_status"}])

    assert workflows.delete("throwaway routine") is True
    assert workflows.run("no such routine")["ok"] is False


# ------------------------------------------------------------- analytics


def test_analytics_overview_has_every_section() -> None:
    from core.analytics import analytics

    overview = analytics.overview()

    for section in (
        "reliability",
        "outcomes",
        "usage",
        "capabilities",
        "learning",
    ):
        assert section in overview, section


def test_analytics_daily_report_is_readable() -> None:
    from core.analytics import analytics

    report = analytics.daily_report()

    assert "JARVIS report" in report, report
    assert "Capabilities:" in report, report


def test_analytics_usage_counts_requests() -> None:
    from core.analytics import analytics

    usage = analytics.usage()

    assert isinstance(usage["top_requests"], list), usage
    assert usage["sample_size"] >= 0, usage


# ----------------------------------------------------- intelligence loop


def test_intelligence_loop_runs_all_stages() -> None:
    from core.intelligence_loop import loop

    result = loop.handle("tell me the current system status")
    stages = [entry["stage"] for entry in result["trace"]]

    for stage in (
        "input",
        "understand",
        "context",
        "memory",
        "policy",
        "decision",
    ):
        assert stage in stages, (stage, stages)

    assert "duration" in result, result


def test_intelligence_loop_rejects_empty_input() -> None:
    from core.intelligence_loop import loop

    assert loop.handle("   ")["ok"] is False


def test_intelligence_loop_explains_itself() -> None:
    from core.intelligence_loop import loop

    loop.handle("what is my system doing right now")
    explanation = loop.explain()

    assert "Request:" in explanation, explanation
    assert "Outcome:" in explanation, explanation


def test_intelligence_loop_priority_scoring() -> None:
    from core.intelligence_loop import loop

    urgent = loop._priority("do this immediately", "action")
    lazy = loop._priority("maybe sometime later", "question")

    assert urgent["score"] > lazy["score"], (urgent, lazy)
    assert 1 <= lazy["score"] <= 10


def test_intelligence_loop_status_lists_stages() -> None:
    from core.intelligence_loop import loop

    status = loop.status()

    assert len(status["stages"]) >= 14, status
    assert status["handled"] >= 1, status


# ------------------------------------------------------------ integration


def test_every_new_module_imports() -> None:
    import importlib

    for name in (
        "core.event_bus",
        "core.context_engine",
        "core.self_improvement",
        "core.workflow_engine",
        "core.analytics",
        "core.intelligence_loop",
        "memory.experience",
        "memory.knowledge_base",
        "learning.behaviour",
        "learning.habits",
        "learning.mistakes",
        "personality.modes",
    ):
        assert importlib.import_module(name) is not None, name


def test_existing_entrypoints_still_import() -> None:
    import importlib

    for name in (
        "config",
        "core.observability",
        "core.tool_schema",
        "security.policy_engine",
        "brains_v2.agent.agent",
        "brains_v2.agent.task_queue",
    ):
        assert importlib.import_module(name) is not None, name


def _main() -> int:
    tests = [
        (name, value)
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    passed = 0
    failed: list[str] = []

    for name, test in tests:
        try:
            test()
            passed += 1
            print(f"PASS {name}")

        except Exception:
            failed.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()

    print(f"\n{passed} passed, {len(failed)} failed")

    if failed:
        print("failed: " + ", ".join(failed))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
