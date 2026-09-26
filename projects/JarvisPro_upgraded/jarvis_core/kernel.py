"""Jarvis feature kernel wiring (S1, S2, S9, S10, S11, S16, S17, S24, S32, S39).

One object graph, built once, injected everywhere. No hidden globals inside
the subsystems themselves -- the singleton here is only a convenience for
entry points that cannot pass the kernel down.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from .analytics import Analytics, ResourceMonitor
from .automation_manager import AutomationManager
from .browser_manager import BrowserManager
from .conversation import ConversationEngine
from .decisions import ContextEngine, DecisionEngine, ManagerRegistry
from .event_bus import EventBus, get_event_bus
from .graph import CycleError, DependencyGraph
from .memory_lifecycle import MemoryStore
from .notes import NotesManager
from .observability import Observability
from .policy import PolicyEngine
from .profile_store import Personality, ProfileStore, get_profile_store
from .reminders import ReminderManager
from .research_manager import ResearchManager
from .agent_runtime import AgentRuntime
from .verification import VerificationEngine
from .learning import ExperienceDB, LearningEngine
from .self_improvement import SelfImprovementEngine
from .knowledge_graph import KnowledgeGraph
from .recovery import RecoveryManager
from .tasks import TaskManager, TaskStore

try:
    from goals.manager import GoalsManager
except Exception:
    GoalsManager = None

try:  # the API layer is optional at import time so a broken transport
    from api.service import ApiService  # cannot take the whole kernel down
except Exception:  # pragma: no cover - only hit when api/ is absent
    ApiService = None


class Kernel:
    def __init__(self, data_dir: Optional[str] = None, subject: str = "owner"):
        suffix = (lambda name: None if not data_dir else f"{data_dir}/{name}")
        self.subject = subject
        self.observability = Observability(suffix("observability.db"))
        self.policy = PolicyEngine(suffix("policy.db"))
        self.analytics = Analytics(suffix("analytics.db"))
        self.resources = ResourceMonitor()
        self.events = get_event_bus(suffix("events.db"))
        self.tasks = TaskManager(TaskStore(suffix("tasks.db")), self.observability, self.resources)
        self.managers = ManagerRegistry(event_bus=self.events)
        self.decisions = DecisionEngine()
        self.context = ContextEngine()
        # Batch 2 subsystems (S3-S8). Constructed here so GUI, voice, Android and
        # background agents all observe the same conversation/memory/profile state.
        self.memory = MemoryStore(suffix("memory_lifecycle.db"), observability=self.observability)
        self.profile = get_profile_store(db_path=suffix("profile.db"), subject=subject)
        self.personality = Personality(profile=self.profile)
        self.conversation = ConversationEngine(suffix("conversation.db"),
                                               personality=self.personality)
        self.notes = NotesManager(suffix("notes.db"))
        self.reminders = ReminderManager(suffix("reminders.db"), policy=self.policy,
                                        profile=self.profile, analytics=self.analytics)
        self._session_id: Optional[str] = None

        # Batch 3 execution managers (S12-S14), registered on the manager
        # registry so selection, fallback, policy, tracing and analytics apply.
        self.automation = AutomationManager(kernel=self)
        self.browser = BrowserManager(suffix("browser.db"), kernel=self)
        self.research = ResearchManager(suffix("research.db"), kernel=self)
        # Batch 3b: verification engine (S19) and bounded agent runtime (S18).
        self.verification = VerificationEngine(suffix("verification.db"), kernel=self)
        self.agents = AgentRuntime(suffix("agents.db"), kernel=self)
        # Self-learning (S40) and self-correction / self-improvement (S20-S21).
        self.learning = LearningEngine(ExperienceDB(
            f"{data_dir}/experience.db" if data_dir else "data/experience.db"))
        self.improvement = SelfImprovementEngine(suffix("improvement.db"), kernel=self,
                                                 learning=self.learning,
                                                 analytics=self.analytics)
        # Batch 3d: knowledge graph with provenance (S22) and corruption
        # detection / automatic recovery (S26-S27).
        self.knowledge = KnowledgeGraph(suffix("knowledge.db"), kernel=self)
        self.recovery_manager = RecoveryManager(suffix("recovery.db"), kernel=self,
                                                data_dir=data_dir)
        # S33 API layer: transport-agnostic surface for the desktop UI, the
        # Android companion and external clients. It delegates to the managers
        # above and owns no business logic of its own.
        self.api = ApiService(suffix("api.db"), kernel=self) if ApiService else None
        # S41 Goals: wired to TaskManager so milestone completion auto-creates linked tasks.
        self.goals = GoalsManager(data_dir=suffix("goals"), task_manager=self.tasks) \
            if GoalsManager else None
        if self.goals:
            # Subscribe to task-completion events so milestone tasks can trigger goal updates
            self.events.subscribe(
                "task:completed",
                lambda ev: self._on_task_completed(ev),
                description="goals:task_completion_handler"
            )
        for name, manager in (("automation", self.automation),
                              ("browser", self.browser),
                              ("research", self.research),
                              ("agents", self.agents),
                              ("self_improvement", self.improvement),
                              ("knowledge", self.knowledge),
                              ("recovery", self.recovery_manager),
                              *((("api", self.api),) if self.api is not None else ())):
            self.managers.register(name, manager, capabilities=[manager.capability],
                                   probe=lambda m=manager: bool(m.health().get("available", True)))

        # Publish kernel-ready lifecycle event
        self.events.emit("kernel:ready", {"subject": subject}, source="kernel")

    # ---- integrated request understanding (conversation -> context -> memory/profile) ----
    def session(self, surface: str = "text") -> str:
        """Shared conversation session for a surface, created on first use."""
        if self._session_id is None:
            self._session_id = self.conversation.start_session(surface)
        return self._session_id

    def understand(self, text: str, candidates: Any = (), surface: str = "text",
                   audience: str = "owner") -> Dict[str, Any]:
        """Run one request through conversation, context, memory and profile.

        Returns the assembled understanding used by the brain/decision layers:
        detected signals, clarification (if the request is ambiguous), relevant
        memories the audience is allowed to see, profile constraints and the
        style directives the response must honour. Never raises for missing
        subsystems - each stage degrades independently and reports why.
        """
        session_id = self.session(surface)
        result: Dict[str, Any] = {"text": text, "session": session_id, "surface": surface,
                                  "degraded": []}
        turn = self.conversation.analyse(session_id, text, candidates=tuple(candidates))
        result["turn"] = turn.to_dict()
        result["needs_clarification"] = turn.needs_clarification
        result["clarification"] = turn.clarification
        result["style"] = turn.style_directives

        try:
            memories = self.memory.recall(text, audience=audience, limit=5)
            result["memories"] = [m.to_dict() for m in memories]
            for mem in memories:
                self.context.add("memory", mem.content, "memory", confidence=mem.confidence)
        except Exception as exc:
            result["degraded"].append(f"memory: {type(exc).__name__}: {exc}")
            result["memories"] = []

        try:
            result["profile"] = self.profile.snapshot()
            result["constraints"] = self.profile.constraints()
            result["next_goal"] = self.profile.next_goal()
        except Exception as exc:
            result["degraded"].append(f"profile: {type(exc).__name__}: {exc}")

        try:
            self.context.add("conversation", text, "conversation", confidence=0.8)
            result["context"] = self.context.assemble()
        except Exception as exc:
            result["degraded"].append(f"context: {type(exc).__name__}: {exc}")

        result["emotion"] = self.personality.emotional_context(self.conversation.mood(session_id))
        result["presentation"] = self.personality.render(
            surface if surface in ("gui", "voice", "text", "android", "agent") else "text",
            turn.style_directives)
        return result

    def remember(self, content: str, **kwargs: Any) -> Any:
        """Capture a memory through the kernel so privacy classification applies."""
        return self.memory.capture(content, **kwargs)

    # ---- convenience used by managers / GUI ----
    def begin(self, label: str) -> str:
        return self.observability.start_trace(label)

    def guard(self, scope: str, action: str = "", timeout: float = 30.0,
              trace_id: Optional[str] = None) -> Dict[str, Any]:
        return self.policy.guard(self.subject, scope, action, timeout, trace_id)

    def health(self) -> Dict[str, Any]:
        return {
            "observability": self.observability.health(),
            "managers": self.managers.health_check(),
            "events": self.events.stats(),
            "resources": self.resources.health(),
            "tasks": self.tasks.summary(),
            "analytics": self.analytics.dashboard()["overall"],
            "pending_approvals": self.policy.pending_approvals(),
            "memory": self.memory.stats(),
            "notes": self.notes.stats(),
            "reminders": self.reminders.stats(),
            "automation": self.automation.health(),
            "browser": self.browser.health(),
            "research": self.research.health(),
            "agents": self.agents.health(),
            "verification": self.verification.health(),
            "learning": self.learning.stats(),
            "improvement": self.improvement.health(),
            "knowledge": self.knowledge.health(),
            "recovery": self.recovery_manager.health(),
            "goals": self.goals.get_summary() if self.goals else {"available": False},
        }

    def recover(self) -> Dict[str, Any]:
        """Startup recovery: expire stale permissions, resume safe tasks."""
        return {
            "permissions_expired": self.policy.purge_expired(),
            "tasks": self.tasks.recover(),
            "memory_decay": self.memory.decay(),
            "reminders_due": len(self.reminders.due()),
        }

    # ---- goal ↔ task integration ----
    def _on_task_completed(self, event: Any) -> None:
        """When a task linked to a goal milestone completes, update the milestone."""
        if self.goals is None:
            return
        data = getattr(event, "data", {}) or {}
        task_id = data.get("task_id")
        payload = data.get("payload", {})
        goal_id = payload.get("goal_id")
        milestone_id = payload.get("milestone_id")
        if goal_id and milestone_id:
            self.goals.complete_milestone(goal_id, milestone_id)
            self.events.emit("milestone:completed",
                             {"goal_id": goal_id, "milestone_id": milestone_id, "task_id": task_id},
                             source="kernel")


_KERNEL: Optional[Kernel] = None
_LOCK = threading.Lock()


def get_kernel(data_dir: Optional[str] = None) -> Kernel:
    global _KERNEL
    with _LOCK:
        if _KERNEL is None:
            _KERNEL = Kernel(data_dir)
        return _KERNEL


__all__ = ["Kernel", "get_kernel", "CycleError", "DependencyGraph", "EventBus", "get_event_bus"]
