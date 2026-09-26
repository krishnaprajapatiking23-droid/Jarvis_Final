from brains_v2.trace import trace
"""
=========================================================
Jarvis Pro V8 Intelligent Router
Part 1
=========================================================
"""

from brains_v2.intent import detect
from brains_v2.llm.manager import ask
from brains_v2.parser import parser
from brains_v2.background import background
from brains_v2.automation_manager import automation_manager
from brains_v2.orchestrator import orchestrator

from brains_v2.performance import performance
from brains_v2.optimizer import optimizer

from automation.apps import match_app, open_app, close_app, is_close_request
from conversation.request_type import is_action_request
from automation.browser import open_website
from automation.desktop import desktop

import automation.windows as windows

from automation.clipboard import clipboard
from automation.power import power
from brains_v2.manager_modules.notes_manager import process as process_notes
from brains_v2 import core_bridge

import logging

log = logging.getLogger("jarvis.brain.router")


class Router:

    def __init__(self):

        self.total_routes = 0
        self.agent_routes = 0
        self.chat_routes = 0
        self.automation_routes = 0
        self.failed_routes = 0

        self.last_command = None
        self.last_intent = None
        self.last_route = None
        self.last_result = None

    # =====================================================
    # Runtime
    # =====================================================

    def _start(self, command):

        self.total_routes += 1
        self.last_command = command

        try:
            performance.route_started(command)
        except Exception:
            pass

        try:
            optimizer.learn(command)
        except Exception:
            pass

    def _finish(self, route_type, result=None):

        self.last_route = route_type
        self.last_result = result

        try:
            performance.route_finished(route_type)
        except Exception:
            pass

    def statistics(self):

        return {

            "total_routes": self.total_routes,
            "agent_routes": self.agent_routes,
            "automation_routes": self.automation_routes,
            "chat_routes": self.chat_routes,
            "failed_routes": self.failed_routes,
            "last_route": self.last_route,
            "last_intent": self.last_intent

        }

    # =====================================================
    # Main Router
    # =====================================================

    def route(self, command, decision=None):

        self._start(command)

        parsed = parser.parse(command)

        intent = detect(command)

        self.last_intent = intent

        text = command.lower()

        trace("=" * 60)
        trace("COMMAND :", command)
        trace("PARSER  :", parsed)
        trace("INTENT  :", intent)
        trace("=" * 60)

        # =================================================
        # Exit
        # =================================================

        if intent == "exit":

            result = {

                "type": "exit",
                "reply": "Goodbye."

            }

            self._finish("exit", result)

            return result

        # =================================================
        # Planner Agent
        # =================================================

        planner = orchestrator.get("planner")

        if planner:

            try:

                plan = planner.execute(command)

                if plan.get("handled"):

                    self.agent_routes += 1

                    result = {

                        "type": "planner",
                        "result": plan

                    }

                    self._finish("planner", result)

                    return result

            except Exception as error:

                # A planner failure must never destroy the conversation:
                # log the real reason and fall through to conversation.
                log.warning("planner failed on %r: %r", command, error)

                trace("ROUTER -> planner failed:", error)

        # =================================================
        # Multi-Agent Dispatcher
        # =================================================

        try:

            agent_result = orchestrator.dispatch(command)

            if agent_result:

                self.agent_routes += 1

                result = {

                    "type": "agent",
                    "result": agent_result

                }

                self._finish("agent", result)

                return result

        except Exception as e:

            log.warning("dispatcher failed on %r: %r", command, e)

        # =================================================
        # Automation
        # =================================================

        if intent == "automation":

            target = match_app(command)

            # "Tell me about Notepad." names an application but asks
            # for information, so it must never reach open_app().
            if target and not is_action_request(command):

                log.info(
                    "information request about %r; not automation",
                    target,
                )

                trace("ROUTER -> information request, falling through")

                target = ""

            if not target:

                # No application was named, so this is not automation at
                # all ("I've explained this three times...").  Fall through
                # to the conversation system instead of "opening" nothing.
                log.info(
                    "no automation target in %r; treating as conversation",
                    command,
                )

                trace("ROUTER -> no automation target, falling through")

            else:

                self.automation_routes += 1

                # "Close it." arrives here already resolved to
                # "close notepad", so the verb decides the action.  It used
                # to fall into open_app(), which focused the window and
                # answered "Notepad is already open."
                if is_close_request(command):
                    outcome = close_app(command)

                else:
                    outcome = open_app(command)

                result = {

                    "type": "automation",
                    "result": outcome

                }

                self._finish("automation", result)

                return result

        # =================================================
        # Browser
        # =================================================

        if intent == "browser":

            self.automation_routes += 1

            result = {

                "type": "browser",
                "result": automation_manager.execute(command)

            }

            self._finish("browser", result)

            return result

        # =================================================
        # Desktop
        # =================================================

        if intent == "desktop":

            self.automation_routes += 1

            result = {

                "type": "desktop",
                "result": desktop.open_desktop()

            }

            self._finish("desktop", result)

            return result

        # =================================================
        # Windows
        # =================================================

        if intent == "windows":

            self.automation_routes += 1

            try:

                if "minimize" in text:

                    output = windows.minimize()

                elif "maximize" in text:

                    output = windows.maximize()

                elif "desktop" in text:

                    output = windows.show_desktop()

                elif "switch" in text:

                    output = windows.switch_window()

                elif "close" in text:

                    output = windows.close()

                else:

                    output = "Unknown windows command."

            except Exception as e:

                output = str(e)

            result = {

                "type": "windows",
                "result": output

            }

            self._finish("windows", result)

            return result

        # =================================================
        # Clipboard
        # =================================================

        if "clipboard" in text:

            self.automation_routes += 1

            try:

                output = clipboard.execute(command)

            except Exception as e:

                output = str(e)

            result = {

                "type": "clipboard",
                "result": output

            }

            self._finish("clipboard", result)

            return result

        # =================================================
        # Power
        # =================================================

        if any(
            word in text
            for word in [
                "shutdown",
                "restart",
                "sleep"
            ]
        ):

            self.automation_routes += 1

            try:

                output = power.execute(command)

            except Exception as e:

                output = str(e)

            result = {

                "type": "power",
                "result": output

            }

            self._finish("power", result)

            return result

        # =================================================
        # Memory
        # =================================================

        if intent == "memory":

            # The memory engine stores / corrects / recalls and returns the
            # sentence the user should hear.  The old placeholder reply was
            # internal status wording and it hid the real answer to
            # "What language does it use?".
            answer = ""

            try:
                from memory.memory_engine import process_memory

                answer = process_memory(command) or ""

            except Exception as error:  # pragma: no cover - defensive
                log.warning("memory engine failed on %r: %r", command, error)

            if not answer:
                # Not actually a memory instruction - let the conversation
                # system own the turn instead of answering with a label.
                log.info("memory intent produced no reply for %r", command)

                trace("ROUTER -> memory intent had no answer, falling through")

            else:

                result = {

                    "type": "memory",
                    "reply": answer

                }

                self._finish("memory", result)

                return result

        # =================================================
        # Notes
        # =================================================

        if intent == "notes":

            result = process_notes(command)

            if result:

                self._finish("notes", result)

                return result

        # =================================================
        # Profile
        # =================================================
        #
        # BUG FIX: "What do you know about my preferences?" scored as
        # "knowledge" and was answered by the model (or the model-unavailable
        # fallback). Section 8 requires it to reach the profile store, which
        # can answer it from persisted attributes with no model at all. This
        # runs before the knowledge branch because that branch is what used
        # to swallow it.

        profile_answer = core_bridge.handle_profile(command)

        if profile_answer:

            result = {

                "type": "profile",
                "reply": profile_answer.get("reply", "")

            }

            self._finish("profile", result)

            return result

        # =================================================
        # Knowledge
        # =================================================

        if intent == "knowledge":

            self.chat_routes += 1

            result = {

                "type": "knowledge",
                "reply": ask(command)

            }

            self._finish("knowledge", result)

            return result

        # =================================================
        # Coding
        # =================================================

        if intent == "coding":

            self.chat_routes += 1

            result = {

                "type": "coding",
                "reply": ask(command)

            }

            self._finish("coding", result)

            return result

        # =================================================
        # Research
        # =================================================

        if intent == "research":

            self.chat_routes += 1

            # Prefer the real research manager (multi-source, conflict
            # detection, provenance); fall back to the model only when it has
            # no fetcher configured.
            researched = core_bridge.handle_research(command)

            result = {

                "type": "research",
                "reply": researched["reply"] if researched else ask(command)

            }

            self._finish("research", result)

            return result

        # =================================================
        # Business
        # =================================================

        if intent == "business":

            self.chat_routes += 1

            result = {

                "type": "business",
                "reply": ask(command)

            }

            self._finish("business", result)

            return result

        # =================================================
        # Vision
        # =================================================

        if intent == "vision":

            self.agent_routes += 1

            # BUG FIX: this used to answer the placeholder string
            # "Vision Agent Selected." and do nothing at all.
            result = {

                "type": "vision",
                "reply": core_bridge.handle_vision(command)["reply"]

            }

            self._finish("vision", result)

            return result

        # =================================================
        # Internet
        # =================================================

        if intent == "internet":

            self.automation_routes += 1

            try:

                output = automation_manager.execute(command)

            except Exception as e:

                output = str(e)

            result = {

                "type": "internet",
                "result": output

            }

            self._finish("internet", result)

            return result

        # =================================================
        # Security
        # =================================================

        if intent == "security":

            self.agent_routes += 1

            # BUG FIX: placeholder "Security Agent Selected." replaced with
            # the real policy engine in jarvis_core.
            result = {

                "type": "security",
                "reply": core_bridge.handle_security(command)["reply"]

            }

            self._finish("security", result)

            return result

        # =================================================
        # Mobile
        # =================================================

        if intent == "mobile":

            self.agent_routes += 1

            # BUG FIX: placeholder "Mobile Agent Selected." replaced with the
            # real companion-server state.
            result = {

                "type": "mobile",
                "reply": core_bridge.handle_mobile(command)["reply"]

            }

            self._finish("mobile", result)

            return result

        # =================================================
        # Task
        # =================================================

        if intent == "task":

            self.agent_routes += 1

            # BUG FIX: this answered "Task received." and created NO task.
            # It now goes to jarvis_core.tasks (TaskManager/TaskStore), the
            # same manager the kernel and the test suite use.
            handled = core_bridge.handle_task(command)

            result = {

                "type": "task",
                "reply": (handled or {}).get(
                    "reply", "I couldn't work out what task you meant."
                )

            }

            self._finish("task", result)

            return result

        # =================================================
        # Browser URL Detection
        # =================================================

        if (
            text.startswith("https://")
            or text.startswith("http://")
            or text.startswith("www.")
        ):

            self.automation_routes += 1

            try:

                output = open_website(command)

            except Exception as e:

                output = str(e)

            result = {

                "type": "browser",
                "result": output

            }

            self._finish("browser", result)

            return result

        # =================================================
        # Skills and plugins
        # =================================================
        #
        # BUG FIX: the skill registry and plugin system were both dead on
        # import, so nothing ever consulted them and arithmetic like
        # "what is 25 * 4" fell through to the (offline) model.

        skill_result = core_bridge.handle_skill(command)

        if skill_result:

            self.agent_routes += 1

            result = {

                "type": "skill",
                "reply": skill_result.get("reply", "")

            }

            self._finish("skill", result)

            return result

        # =================================================
        # Smart Chat Fallback
        # =================================================

        self.chat_routes += 1

        try:

            reply = ask(command)

        except Exception as e:

            self.failed_routes += 1

            reply = f"Router Error: {e}"

        result = {

            "type": "chat",
            "reply": reply

        }

        self._finish("chat", result)

        return result


router = Router()

# =====================================================
# END OF FILE
# =====================================================