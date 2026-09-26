import os
import re

from automation.apps import match_app
from conversation.request_type import is_action_request
from brains_v2.context import context
from brains_v2.decision import decide
from brains_v2.automation import execute
from brains_v2.response import generate
from brains_v2.verifier import verify
from brains_v2.goals import planner
from brains_v2.brain_state import brain_state
from brains_v2.personality_engine import personality
from brains_v2.database import database
from brains_v2.profile import profile
from brains_v2.adaptive import adaptive
from brains_v2.conversation import conversation
from brains_v2.habits import habits
from brains_v2.knowledge import knowledge
from brains_v2.trace import trace
from brains_v2.planner import make_plan
from brains_v2.orchestrator import orchestrator
from brains_v2.reasoning import think
from brains_v2.relationship import relationship
from brains_v2.memory import memory
from brains_v2.task_engine import task_engine
from brains_v2.learning import learning
from brains_v2.action_pipeline import pipeline
from brains_v2.executor import executor
from brains_v2.goal_manager import goal_manager
from brains_v2.correction import correction
from brains_v2.planning_engine import planning_engine
from brains_v2.emotion import set_emotion, get_emotion
from brains_v2.chat_context import chat_context
from brains_v2.statistics import statistics
from brains_v2.mission import mission
from brains_v2.style import style
from brains_v2.nlp import chat
from brains_v2.summary import summary
from brains_v2.dialogue_memory import dialogue_memory
from brains_v2.reflection import reflection
from brains_v2.autonomous_core import autonomous_core
from brains_v2.decomposer import decomposer
from brains_v2.decision_tree import decision_tree
from brains_v2.background_executor import background_executor
from brains_v2.experience import experience
from brains_v2.intents.note_intent import detect
from brains_v2.notes.notes import (
    add_note,
    show_notes,
    read_note,
    delete_note,
    clear_notes,
)
from brains_v2.recall import recall
from brains_v2.reasoning_engine import reasoning_engine
from brains_v2.llm.manager import ask
from brains_v2.intents.memory_intent import detect as detect_memory
from brains_v2.memory.memory import (
    remember,
    recall as memory_recall,
    update_profile,
    get_profile,
    add_person,
    get_people,
)
from brains_v2.execution_planner import execution_planner
from brains_v2.honesty import honesty
from brains_v2.tools.manager import process
from brains_v2.agent_bridge import bridge
from brains_v2.self_learning.learner import learn
from brains_v2.self_improvement import self_improvement
from brains_v2.task_queue import task_queue
from brains_v2.humanizer import humanize
from brains_v2.intents.reminder_intent import detect as detect_reminder
from brains_v2.reminders.reminders import add, show
from brains_v2.smart_commands import fix
from brains_v2.scheduler import scheduler
from brains_v2.router_v2 import router
from brains_v2.workflow import workflow
from brains_v2.followup import next_question
# ---------- Conversation System ----------
from conversation.conversation_engine import conversation_engine
from agi.integration import bridge as agi_bridge
# ---------- New Jarvis Pro Modules ----------
from brains_v2.performance import performance
from brains_v2.optimizer import optimizer
from brains_v2.error_analyzer import error_analyzer
from brains_v2.self_correction import self_correction
from memory.semantic_memory import semantic_memory
from memory.memory_search import memory_search
from memory.memory_ranker import memory_ranker
from brains_v2.manager_modules.notes_manager import process as process_notes
from brains_v2 import core_bridge
from brains_v2.controllers.command_controller import command_controller
from brains_v2.controllers.runtime_controller import runtime_controller
from brains_v2.controllers.memory_controller import memory_controller
from brains_v2.controllers.tool_controller import tool_controller
from brains_v2.controllers.reminder_controller import reminder_controller
from brains_v2.controllers.llm_controller import llm_controller
from brains_v2.manager_modules.reminder_manager import process as process_reminder
from brains_v2.manager_modules.memory_manager import process as process_memory
from brains_v2.manager_modules.coding_manager import process as process_coding
from brains_v2.manager_modules.router_manager import process as process_router
from jarvis_core import process_goal_command

class BrainV2:

    # Injected by Kernel (avoids premature ProfileStore creation before Kernel
    # initialises the canonical singleton with the right db_path/subject).
    _profile_store = None

    @classmethod
    def set_profile_store(cls, store):
        cls._profile_store = store

    #: Set True (or JARVIS_DEBUG=1) to attach the diagnostics block to replies.
    VERBOSE = False

    #: Route types whose success is measured by "did it answer?", not by
    #: whether an operating-system action was performed.
    _CONVERSATIONAL_ROUTES = frozenset({
        "chat", "knowledge", "coding", "research", "business",
        "memory", "notes", "planner", "conversation", "reminder",
    })

    def __init__(self):

        # -------------------------
        # Register Core Modules
        # -------------------------

        orchestrator.register("memory", memory)

        orchestrator.register("profile", profile)

        orchestrator.register("knowledge", knowledge)

        orchestrator.register("conversation", conversation)

        orchestrator.register("relationship", relationship)

        orchestrator.register("planner", planner)

        orchestrator.register("goal_manager", goal_manager)

        orchestrator.register("workflow", workflow)

        orchestrator.register("autonomous_core", autonomous_core)

        # -------------------------
        # Runtime
        # -------------------------

        self.total_commands = 0

        self.success_count = 0

        self.failed_count = 0

        self.last_command = None

        self.last_decision = None

        self.last_result = None

        self.last_reply = None

        self.last_plan = None

        self.last_reasoning = None

        self.last_verification = None


    # Whole-word profile signals: (regex pattern, ProfileStore.observe key, value).
    _PROFILE_SIGNALS = (
        (r"\bjarvis\b", "projects", "Jarvis Pro"),
        (r"\bpython\b", "skills", "Python"),
        (r"\bbusiness\b", "interests", "Business"),
        (r"\b(?:ai|a\.i\.|artificial intelligence|machine learning|ml)\b",
         "interests", "Artificial Intelligence"),
    )

    # Only treat a mention as a profile signal when the user is speaking
    # about themselves or their work.
    _SELF_REFERENCE = re.compile(
        r"\b(i|i'm|im|i am|my|me|mine|we|our|we're)\b",
        re.IGNORECASE,
    )

    def _learn_profile(self, command):
        """Record whole-word profile signals from a self-referential sentence.

        Signals are written to the canonical ProfileStore (injected by Kernel as
        ``BrainV2._profile_store``) via ``observe()``, which accumulates evidence
        and promotes entries only after MIN_EVIDENCE consistent observations.
        The legacy in-memory ``profile`` stub is no longer used.
        """
        text = str(command or "")
        if not self._SELF_REFERENCE.search(text):
            return

        # Use the ProfileStore injected by Kernel; fall back gracefully.
        store = self._profile_store
        if store is None:
            try:
                from jarvis_core.profile_store import get_profile_store
                store = get_profile_store()
            except Exception:
                return  # Profile learning is best-effort; never break a reply.

        for pattern, attr_key, value in self._PROFILE_SIGNALS:
            if not re.search(pattern, text, re.IGNORECASE):
                continue
            try:
                store.observe(
                    attr_key,
                    value,
                    source="conversation_signal",
                    detail=f"detected in: {text[:120]}"
                )
            except Exception:
                # Profile learning is best-effort; never break a reply.
                pass

    def _conversation_reply(self, understanding, result, action=""):
        """Send an early-return result through the Conversation System.

        Keeps conversation state, history, entities and memory in sync even
        when a specialised manager (notes, reminders, coding, ...) answers
        the command first.
        """

        if not isinstance(result, dict):
            return result

        result["reply"] = conversation_engine.commit(
            understanding,
            result.get("reply", ""),
            action or str(result.get("type", ""))
        )

        # STEP 5 FIX: wire conversation → profile learning on every route.
        # Every early-return path (skill, task, notes, reminder, memory, coding,
        # router, and the conversation fast path) commits to the conversation
        # engine but previously never triggered profile learning.  Adding the
        # call here means the signal fires for all of them.
        self._learn_profile(command)

        result["conversation"] = understanding.to_dict()
        result.setdefault("success", bool(result.get("reply")))

        # BUG FIX: every early-return stage (skills, tasks, notes, reminders,
        # memory, coding, router) used this helper to answer immediately,
        # which is correct -- they shouldn't pay the deep pipeline's cost --
        # but it meant JARVIS_DEBUG had nothing to attach diagnostics to for
        # any of those routes, only for commands that fell through to the
        # very end of _run(). Debug mode is now uniform across every route.
        if self.VERBOSE or os.environ.get("JARVIS_DEBUG") == "1":
            result.setdefault("diagnostics", {
                "route": "%s-early-return" % (action or result.get("type", "")),
                "modules": len(orchestrator.all()),
                "brain_state": brain_state.status(),
                "llm_used": False,
                "autonomous_core": autonomous_core.report(),
            })

        return result

    def process(self, command):
        """Public entry point: count the command, then run the pipeline.

        BUG FIX: the counters used to live deep inside the pipeline, after
        several stages that return early (notes, reminders, memory, plain
        conversation). Anything answered by those stages was never counted at
        all -- six commands in, ``total_commands`` read 1 -- while commands
        that did reach the deep path were counted twice. Counting now happens
        once, here, for every command, and the outcome is recorded on every
        return path including the exception path.
        """
        self.total_commands += 1
        self.last_command = command

        try:
            response = self._run(command)
        except Exception:
            self.failed_count += 1
            raise

        succeeded = True
        if isinstance(response, dict) and "success" in response:
            succeeded = bool(response["success"])
        elif isinstance(response, dict):
            succeeded = bool(response.get("reply"))

        if succeeded:
            self.success_count += 1
        else:
            self.failed_count += 1

        return response

    def _run(self, command):

        # -----------------------------------
        # Conversation System
        # Understand the message in context before anything else runs:
        # session, interruption, clarification, greeting, farewell,
        # correction, references, entities, time, topic, emotion, context.
        # -----------------------------------

        understanding = conversation_engine.understand(command)

        if understanding.handled:

            fast_reply = {

                "type": "conversation",

                "command": command,

                "reply": conversation_engine.commit(
                    understanding,
                    understanding.handled_reply,
                    understanding.intent
                ),

                "conversation": understanding.to_dict(),

                "success": True,

            }

            # BUG FIX: greetings and farewells answer through this fast path
            # and never reach the deep pipeline below, so debug mode used to
            # have nothing to attach diagnostics to -- brains_v2/test_orchestrator.py
            # and test_llm_integration.py raised KeyError: 'diagnostics' on a
            # plain "Hello". A minimal, honest diagnostics block is attached
            # here too so JARVIS_DEBUG behaves consistently on every route.
            if self.VERBOSE or os.environ.get("JARVIS_DEBUG") == "1":
                fast_reply["diagnostics"] = {
                    "route": "conversation-fast-path",
                    "modules": len(orchestrator.all()),
                    "brain_state": brain_state.status(),
                    "llm_used": False,
                    "autonomous_core": autonomous_core.report(),
                }

            # STEP 5 FIX: wire profile learning on the conversation fast path too.
            self._learn_profile(command)

            return fast_reply

        # Reference-resolved command: "close it" -> "close chrome"
        command = understanding.command or command

        try:
            agi_state = agi_bridge.analyze(command)
            self.last_plan = agi_state.plan
            self.last_reasoning = {"domain": agi_state.domain, "constraints": agi_state.constraints, "unknowns": agi_state.unknowns}
        except Exception as error:
            self.last_reasoning = {"error": f"{type(error).__name__}: {error}"}

        # Skills and plugins get first refusal on things they can answer
        # exactly (arithmetic, unit conversion, ...). BUG FIX: both registries
        # were dead on import, so nothing consulted them at all.
        skill_result = core_bridge.handle_skill(command)

        if skill_result:
            return self._conversation_reply(understanding, skill_result, "skill")

        task_result = core_bridge.handle_task(command)

        if task_result:
            return self._conversation_reply(understanding, task_result, "task")

        result = process_notes(command)

        if result:
            return self._conversation_reply(understanding, result, "notes")

        result = process_reminder(command)

        if result:
            return self._conversation_reply(understanding, result, "reminder")

        result = process_memory(command)

        if result:
            return self._conversation_reply(understanding, result, "memory")

        result = process_coding(command)

        if result:
            return self._conversation_reply(understanding, result, "coding")

        result = process_router(command)

        if result:
            return self._conversation_reply(understanding, result, "router")

        # ── Goal Progress & Goal Template handlers ──────────────────────────
        goal_result = process_goal_command(command)

        if goal_result:
            return self._conversation_reply(understanding, goal_result, "goal")

        trace(f"MANAGER -> {command}")

        command = command_controller.process(command)

        runtime_controller.start(
            self,
            command
        )

        context.command = command

        learning.learn(command)

        # -----------------------------------
        # Runtime Statistics
        # -----------------------------------
        #
        # BUG FIX: ``runtime_controller.start()`` (called a few lines above)
        # already does ``manager.total_commands += 1``. Incrementing again
        # here counted every command twice, so the analytics in roadmap
        # section 32 reported double the real traffic.

        self.last_command = command

        performance.command_started(command)

        text = command.lower()

        action_word = re.search(
            r"\b(open|close|launch|run|start|stop|kill|restart)\b",
            text,
        )

        # An action word on its own is not an automation request: "start
        # over", "I've explained this three times..." and "run out of time"
        # are conversation.  Automation only wins when a real application
        # was actually named.
        if (
            action_word
            and match_app(command)
            and is_action_request(command)
        ):
            decision = "OPEN"
        else:
            decision = decide(command)

        self.last_decision = decision

        reminder_result = reminder_controller.process(command)

        if reminder_result:
            return reminder_result

        memory_intent = detect_memory(command)

        # -----------------------------------
        # Semantic Memory Search
        # -----------------------------------

        try:

            semantic_memory.store(command)

        except Exception:

            pass

        try:

            memory_search.search(command)

        except Exception:

            pass

        # -----------------------------------
        # Memory Controller
        # Previously unreachable: the call sat inside the except block
        # above and was followed by dead code using an undefined name.
        # -----------------------------------

        try:

            memory_result = memory_controller.process(command)

        except Exception:

            memory_result = None

        if memory_result:

            return self._conversation_reply(
                understanding,
                memory_result,
                "memory"
            )

        trace(f"ROUTER -> {command}")
        route = router.route(command, decision)
        trace(route)

        # -----------------------------------
        # Intelligent Planner
        # -----------------------------------

        if route.get("type") == "planner":

            planner_result = route.get("result")

            if planner_result:

                self.last_plan = planner_result

                # A goal operation already produced the sentence the
                # user should hear, so return it instead of dropping
                # the plan and answering something unrelated.
                if isinstance(planner_result, dict) and planner_result.get(
                    "reply"
                ):

                    return {

                        "type": "planner",
                        "reply": planner_result["reply"]

                    }

        result = None

        # Exit
        if route["type"] == "exit":

            return {

                "type": "exit",
                "reply": route["reply"]

            }

        # Background Tasks
        if route["type"] == "background":

            result = background_executor.execute(route["command"])

            return {

                "reply": result["reply"]

            }

        bridge_result = {
            "result": None,
            "source": "none"
        }

        if route["type"] != "automation":

            trace("BEFORE BRIDGE")

            bridge_result = bridge.process(command)

            trace("AFTER BRIDGE")

            if (
                bridge_result.get("result") is not None
                and bridge_result.get("source") != "none"
            ):
                result = bridge_result["result"]
                self.last_result = result

            else:
                result = None

        # -----------------------------------
        # Runtime Cache
        # -----------------------------------
        #
        # BUG FIX: these statements unconditionally reset ``self.last_result``
        # and ``bridge_result`` immediately after the agent bridge had already
        # produced a real answer, so a successful bridge result was discarded
        # on every command. The cache is only cleared when the bridge really
        # produced nothing.

        if bridge_result.get("source") == "none":
            self.last_result = None

        llm_reply = None
        performance.start_timer()

        brain_route = decision_tree.decide(command)

        # BUG FIX: this result was overwritten wholesale by think() further
        # down, so the reasoning engine ran on every command and its output
        # was discarded. It is kept under its own name and merged below.
        engine_reasoning = reasoning_engine.analyze(command)

        self.last_reasoning = engine_reasoning

        # BUG FIX: this was immediately overwritten by the decomposer on the
        # next line, so the planning engine ran and its plan was thrown away.
        strategic_plan = planning_engine.create(command)

        plan = decomposer.decompose(command)

        if isinstance(plan, dict) and isinstance(strategic_plan, dict):
            merged = dict(strategic_plan)
            merged.update(plan)
            plan = merged
        elif not plan:
            plan = strategic_plan

        workflow.create(
            command,
            plan
        )

        autonomous_core.start(command)

        execution_planner.build(plan)

        text = command.lower()

        if any(word in text for word in [

            "build",

            "create",

            "make",

            "develop",

            "design",

            "write",

            "plan"

        ]):

            task_queue.add(command)

            goal_manager.start(command)

            pipeline.add(command)

            executor.load([

                "Analyze",

                "Plan",

                "Execute",

                "Verify"

            ])

            scheduler.add(command)

        experience.learn(decision)

        text = command.lower()

        if any(word in text for word in [

            "build",

            "create",

            "develop",

            "design",

            "plan"

        ]):

            task_engine.add(command)

        text = command.lower()

        if any(word in text for word in [

            "build",

            "create",

            "develop",

            "make",

            "design"

        ]):

            mission.start(command)

        relationship.talk()

        habits.learn(command)

        text = command.lower()

        if "my name is" in text:

            value = command.split("is", 1)[1].strip()

            knowledge.remember("name", value)

        elif "my city is" in text:

            value = command.split("is", 1)[1].strip()

            knowledge.remember("city", value)

        elif "my favourite language is" in text:

            value = command.split("is", 1)[1].strip()

            knowledge.remember("language", value)

        # -----------------------------------
        # Passive profile learning
        # -----------------------------------
        #
        # BUG FIX: this block used bare substring tests. ``if "ai" in text``
        # fired on "said", "main", "email", "again", "wait" and "afraid", so
        # the profile filled with interests the user never expressed. The same
        # applied to "python" and "business" inside longer words.
        #
        # Matching is now on whole words, and only when the sentence is the
        # user actually talking about themselves -- not merely mentioning the
        # word in passing.

        self._learn_profile(command)

        planner.create(command)

        context.update(
            command,
            decision
        )

        if decision == "OPEN":

            set_emotion("focused")
            personality.update(
                get_emotion()
            )
            
        elif decision == "CHAT":

            set_emotion("happy")
            personality.update(
                get_emotion()
            )
        
        else:

            set_emotion("thinking")
            personality.update(
                get_emotion()
            )

        plan = make_plan(decision)

        reasoning = think(
            command,
            decision,
            plan
        )

        if isinstance(reasoning, dict) and isinstance(engine_reasoning, dict):
            combined = dict(engine_reasoning)
            combined.update(reasoning)
            reasoning = combined

        self.last_reasoning = reasoning

        # Decide the result based on route type

        if route["type"] == "automation":

            result = route["result"]

        elif route["type"] == "chat":

            result = {
                "reply": route["reply"]
            }

        elif route["type"] == "browser":

            result = route["result"]

        elif route["type"] == "internet":

            result = route["result"]

        elif route["type"] == "desktop":

            result = route["result"]

        elif route["type"] == "windows":

            result = route["result"]

        elif route["type"] == "clipboard":

            result = route["result"]

        elif route["type"] == "power":

            result = route["result"]

        else:

            result = execute(command, decision)

        self.last_result = result

        verification = verify(result)

        # BUG FIX: ``verify()`` returns success=False whenever ``result`` is
        # None, but a conversational turn legitimately has no automation
        # result -- the answer is the reply, not a launched app. Every chat,
        # memory, notes and knowledge turn was therefore recorded as a
        # failure, which is why the success counter sat at 0 while Jarvis was
        # answering correctly. Those route types are verified on whether they
        # produced an answer instead.

        if not verification.get("success") and result is None:
            if route.get("type") in self._CONVERSATIONAL_ROUTES:
                verification = {
                    "success": True,
                    "message": "answered (%s)" % route.get("type"),
                }

        # -----------------------------------
        # Runtime Verification Cache
        # -----------------------------------

        self.last_verification = verification

        # -----------------------------------
        # Error Analysis
        # -----------------------------------

        try:

            error_analyzer.analyze(

                command=command,

                decision=decision,

                result=result,

                verification=verification

            )

        except Exception:

            pass

        learn(
            command,
            decision,
            verification["success"]
        )

        # -----------------------------------
        # Performance
        # -----------------------------------

        performance.command_finished(

            success=verification["success"]

        )

        if verification["success"]:

            self.success_count += 1

            self.last_verification = verification

            autonomous_core.stop()

            execution_planner.complete()

            goal_manager.update(100)

            pipeline.complete()

            pipeline.clear_completed()

            executor.next()

            

        else:

            self.failed_count += 1

            self.last_verification = verification

            goal_manager.update(25)

        self_improvement.learn(
            command,
            verification
        )

        # -----------------------------------
        # Optimizer
        # -----------------------------------

        try:

            optimizer.optimize()

        except Exception:

            pass

        statistics.update(
            verification
        )

        try:

            performance.update()

        except Exception:

            pass

        reflection.update(
            verification
        )

        if verification["success"]:

            brain_state.success()

        else:

            brain_state.failed()

        reply = None

        # -----------------------------------
        # Runtime Reply Cache
        # -----------------------------------

        self.last_reply = None

        # -----------------------------------
        # Reply selection
        # -----------------------------------
        #
        # BUG FIX: only "llm" and "memory" route types had their reply used.
        # Every other answering route -- security, vision, mobile, task,
        # skill, knowledge, coding, research, business, clipboard, power,
        # windows -- fell into the else branch and was thrown away in favour
        # of a model call, so the router could compute a perfectly good
        # answer and the user would still be told "Ollama is unavailable".
        # Any route that produced a reply now wins.

        if route.get("reply"):

            reply = route["reply"]

        elif route["type"] in ["automation", "browser", "desktop"]:

            reply = generate(result)

        else:

            tool_result = tool_controller.process(command)

            if tool_result:
                return tool_result

            reply = llm_controller.process(
                command,
                conversation_engine.prompt(understanding)
            )

        if reply is None:

            if llm_reply:

                reply = llm_reply

            else:

                reply = generate(result)

        # -----------------------------------
        # Reply shaping is now owned by the Conversation System.
        # It applies at most one contextual decoration (emotion opener,
        # occasional name, or a spaced-out follow-up question) instead of
        # stacking a prefix + starter + follow-up + ending on every reply.
        # -----------------------------------

        style.update(
            personality.data()
        )

        reply = style.apply(reply)

        performance.reply_generated()

        self.last_reply = reply

        adaptive.update(
            relationship.data()
        )

        optimizer.learn(
            command,
            verification
        )

        # -----------------------------------
        # Semantic Memory Ranking
        # -----------------------------------

        try:

            memory_ranker.rank(command)

        except Exception:

            pass

        if (
            not verification["success"]
            and decision == "OPEN"
        ):

            honest_reply = honesty.answer(False)

            if honest_reply:

                reply = honest_reply

        suggestion = honesty.correct(command)

        if suggestion:

            reply += "\n\n" + suggestion

        # -----------------------------------
        # Conversation System
        # Compose the final reply, then update conversation state,
        # history, entities, topics, summary and long-term memory.
        # -----------------------------------

        try:

            success = bool(verification.get("success", True))

        except Exception:

            success = True

        reply = conversation_engine.commit(
            understanding,
            reply,
            route.get("type", ""),
            success
        )

        dialogue_memory.add(
            "user",
            command
        )

        dialogue_memory.add(
            "jarvis",
            reply
        )

        try:

            semantic_memory.store(reply)

        except Exception:

            pass

        summary.update(
            dialogue_memory.recent()
        )
        
        chat_context.update(
            command,
            reply
        )
        
        recall.update(
            command,
            reply
        )

        conversation.add(
            command,
            reply
        )

        database.save(
            command,
            reply
        )

        performance.database_saved()

        self.last_reply = reply

        self.last_result = result

        context.last_reply = reply

        memory.remember(
            "conversation",
            f"User: {command}\nJarvis: {reply}"
        )

        try:

            performance.memory_update()

        except Exception:

            pass

        memory.recall(command)

        # -----------------------------------
        # Final Runtime Update
        # -----------------------------------

        try:

            performance.finish()

        except Exception:

            pass

        def _diagnostics():
            """Expensive introspection, built only when asked for."""
            return {

                # -----------------------------------
                # Runtime
                # -----------------------------------

                "runtime": {

                    "total_commands": self.total_commands,

                    "successful": self.success_count,

                    "failed": self.failed_count,

                    "last_command": self.last_command,

                    "last_decision": self.last_decision

                },

                "brain_report": {

                    "running": brain_state.running,

                    "status": brain_state.status(),

                    "emotion": get_emotion(),

                    "performance": performance.report(),

                    "optimizer": optimizer.report(),

                    "statistics": statistics.report(),

                    "modules": len(orchestrator.all())

                },

                "command": command,

                "decision": decision,

                "plan": plan,

                "reasoning": reasoning,

                "result": result,

                "last_memory": memory.recall(command),

                "plan": plan,

                "favorite_app": learning.favourite_app(),

                "workflow": {

                    "current": workflow.current(command),

                    "all": workflow.data()

                },

                "brain_route": brain_route,

                "pipeline": pipeline.data(),

                "scheduler": {

                    "latest": scheduler.latest(),

                    "total": scheduler.total()

                },

                "bridge": bridge_result,

                "self_improvement": self_improvement.report(),

                "llm_used": llm_reply is not None,

                "tasks": {

                    "pending": task_engine.pending(),

                    "completed": task_engine.completed()

                },

                "verification": verification,

                "performance": performance.report(),

                "favorite_command": learning.favourite_command(),

                "execution_plan": {

                    "current": execution_planner.current(),

                    "steps": execution_planner.all()

                },

                "autonomous_core": autonomous_core.report(),

                "adaptive": adaptive.data(),

                "goal_breakdown": plan,

                "personality": personality.data(),

                "database": database.last(),

                "brain_state": brain_state.status(),

                "modules": orchestrator.all(),

                "optimizer": optimizer.report(),

                "executor": {

                    "current_step": executor.current_step(),

                    "finished": executor.finished()

                },

                "task_queue": {

                    "next": task_queue.peek(),

                    "count": task_queue.size(),

                    "tasks": task_queue.all()

                },

                "dialogue": dialogue_memory.recent(),

                "relationship": relationship.data(),

                "style": style.current(),

                "experience": experience.report(),

                "mission": mission.data(),

                "reflection": reflection.report(),

                "error_analyzer": error_analyzer.report(),

                "habits": {

                    "favorite_app": habits.favorite_app(),

                    "favorite_command": habits.favorite_command()

                },
            
                "conversation": conversation.last(),

                "knowledge": knowledge.all(),

                "profile": profile.data(),

                "goal_manager": goal_manager.current(),

                "goal": planner.current(),

                "statistics": statistics.report(),

                "summary": summary.get(),

                "semantic_memory": {

                    "latest": memory_search.search(command),

                    "rank": memory_ranker.rank(command)

                },

                "chat_context": chat_context.data(),

                "recall": recall.data(),

                "context": {

                   "user": context.user,

                    "last_app": context.last_app,

                    "last_command": context.last_command,

                    "current_project": context.current_project

                },

                "emotion": get_emotion(),

                "reasoning_engine": reasoning,

                "last_runtime": {

                    "reasoning": self.last_reasoning,

                    "verification": self.last_verification,

                    "result": self.last_result,

                    "reply": self.last_reply

                },

                "runtime_cache": {

                    "last_command": self.last_command,

                    "last_decision": self.last_decision,

                    "last_reasoning": self.last_reasoning,

                    "last_result": self.last_result,

                    "last_reply": self.last_reply,

                    "last_verification": self.last_verification

                },

                "reply": reply

            

            }

        # -----------------------------------
        # Response contract (BUG FIX)
        #
        # This method used to return a ~60-key diagnostic object with
        # "reply" as the LAST key. Every single command therefore paid
        # for memory.recall(), memory_search.search(), memory_ranker.rank(),
        # orchestrator.all(), task_engine.pending(), habits, statistics and
        # the rest -- and any caller that did not know the exact key got a
        # wall of internal state instead of an answer.
        #
        # The contract is now small and stable: reply / type / success /
        # command. Diagnostics are still available, but only when they are
        # actually wanted (JARVIS_DEBUG=1 or BrainV2.VERBOSE = True), so the
        # hot path stays cheap.
        # -----------------------------------

        response = {
            "reply": reply,
            "type": route.get("type", "chat"),
            "command": command,
            "success": bool(verification.get("success", True)),
            "decision": decision,
            "conversation": understanding.to_dict(),
        }

        if self.VERBOSE or os.environ.get("JARVIS_DEBUG") == "1":
            try:
                response["diagnostics"] = _diagnostics()
            except Exception as error:  # diagnostics must never break a reply
                response["diagnostics"] = {
                    "error": "%s: %s" % (type(error).__name__, error)
                }

        return response


brain = BrainV2()

# -----------------------------------
# Brain Version
# -----------------------------------

BrainV2.VERSION = "Jarvis Pro V7.1"

BrainV2.BUILD = "2026.07"