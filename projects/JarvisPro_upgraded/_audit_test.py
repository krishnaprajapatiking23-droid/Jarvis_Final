"""Comprehensive import audit for all 42 feature categories."""
import sys
sys.path.insert(0, '.')

results = []

def test(name, import_fn):
    try:
        import_fn()
        return (name, "PASS", "")
    except Exception as e:
        return (name, "FAIL", str(e)[:100])

# Category 1: Core Brain & Architecture
results.append(test("jarvis_core.kernel", lambda: __import__('jarvis_core.kernel')))
results.append(test("core.router", lambda: __import__('core.router')))
results.append(test("brains_v2.runtime", lambda: __import__('brains_v2.runtime')))

# Category 2: Context Engine
results.append(test("context.manager", lambda: __import__('context.manager')))
results.append(test("jarvis_core.decisions", lambda: __import__('jarvis_core.decisions')))

# Category 3: Conversation
results.append(test("conversation.manager", lambda: __import__('conversation.manager')))
results.append(test("gui.pages.chat", lambda: __import__('gui.pages.chat')))

# Category 4: Memory System
results.append(test("memory.manager", lambda: __import__('memory.manager')))
results.append(test("jarvis_core.memory_lifecycle", lambda: __import__('jarvis_core.memory_lifecycle')))

# Category 5: Personal Profile
results.append(test("jarvis_core.profile_store", lambda: __import__('jarvis_core.profile_store')))

# Category 6: Personality
results.append(test("personality.manager", lambda: __import__('personality.manager')))

# Category 7: Notes Manager
results.append(test("jarvis_core.notes", lambda: __import__('jarvis_core.notes')))

# Category 8: Reminder Manager
results.append(test("reminders.manager", lambda: __import__('reminders.manager')))
results.append(test("jarvis_core.reminders", lambda: __import__('jarvis_core.reminders')))

# Category 9: Task Management
results.append(test("tasks.manager", lambda: __import__('tasks.manager')))
results.append(test("jarvis_core.tasks", lambda: __import__('jarvis_core.tasks')))

# Category 10: Execution Engine
results.append(test("jarvis_core.graph", lambda: __import__('jarvis_core.graph')))
results.append(test("jarvis_core.agent_runtime", lambda: __import__('jarvis_core.agent_runtime')))

# Category 11: Policy & Permission
results.append(test("jarvis_core.policy", lambda: __import__('jarvis_core.policy')))
results.append(test("security.manager", lambda: __import__('security.manager')))

# Category 12: Computer Automation
results.append(test("jarvis_core.automation_manager", lambda: __import__('jarvis_core.automation_manager')))

# Category 13: Browser Manager
results.append(test("jarvis_core.browser_manager", lambda: __import__('jarvis_core.browser_manager')))

# Category 14: Research Manager
results.append(test("research.manager", lambda: __import__('research.manager')))
results.append(test("jarvis_core.research_manager", lambda: __import__('jarvis_core.research_manager')))

# Category 15: Coding Manager
results.append(test("coding.manager", lambda: __import__('coding.manager')))
results.append(test("gui.pages.coding", lambda: __import__('gui.pages.coding')))

# Category 16: Specialized Managers
results.append(test("brains_v2.manager", lambda: __import__('brains_v2.manager')))

# Category 17: Foreground/Background
results.append(test("background.manager", lambda: __import__('background.manager')))

# Category 18: Autonomous Agent
results.append(test("agents.manager", lambda: __import__('agents.manager')))
results.append(test("agi.engine", lambda: __import__('agi.engine')))

# Category 19: Verification Engine
results.append(test("jarvis_core.verification", lambda: __import__('jarvis_core.verification')))

# Category 20: Self-Correction
results.append(test("brains_v2.self_correction", lambda: __import__('brains_v2.self_correction')))

# Category 21: Self-Improvement
results.append(test("learning.manager", lambda: __import__('learning.manager')))
results.append(test("jarvis_core.self_improvement", lambda: __import__('jarvis_core.self_improvement')))

# Category 22: Knowledge Acquisition
results.append(test("knowledge.manager", lambda: __import__('knowledge.manager')))
results.append(test("jarvis_core.knowledge_graph", lambda: __import__('jarvis_core.knowledge_graph')))

# Category 23: Behaviour Learning
results.append(test("jarvis_core.learning", lambda: __import__('jarvis_core.learning')))

# Category 24: Security
results.append(test("security.manager", lambda: __import__('security.manager')))

# Category 25: Event Bus
results.append(test("event_bus", lambda: __import__('event_bus')))

# Category 26: Testing & Reliability
results.append(test("tests.test_final_hardening", lambda: __import__('tests.test_final_hardening')))

# Category 27: Backup & Recovery
results.append(test("updater.backup_manager", lambda: __import__('updater.backup_manager')))
results.append(test("jarvis_core.recovery", lambda: __import__('jarvis_core.recovery')))

# Category 28: Desktop UI
results.append(test("gui.pages.home", lambda: __import__('gui.pages.home')))
results.append(test("gui.pages.settings", lambda: __import__('gui.pages.settings')))
results.append(test("gui.pages.projects", lambda: __import__('gui.pages.projects')))
results.append(test("gui.pages.memory", lambda: __import__('gui.pages.memory')))
results.append(test("gui.pages.business", lambda: __import__('gui.pages.business')))

# Category 29: Advanced Voice
results.append(test("voice.manager", lambda: __import__('voice.manager')))
results.append(test("brains_v2.voice.pipeline", lambda: __import__('brains_v2.voice.pipeline')))

# Category 30: Vision
results.append(test("vision.vision_engine", lambda: __import__('vision.vision_engine')))
results.append(test("brains_v2.services.vision_service", lambda: __import__('brains_v2.services.vision_service')))
results.append(test("brains_v2.vision_v2.reader", lambda: __import__('brains_v2.vision_v2.reader')))

# Category 31: Android Companion
results.append(test("android.adb_bridge", lambda: __import__('android.adb_bridge')))

# Category 32: Analytics
results.append(test("jarvis_core.analytics", lambda: __import__('jarvis_core.analytics')))

# Category 33: External Integrations
results.append(test("integrations.telegram", lambda: __import__('integrations.telegram')))
results.append(test("integrations.discord", lambda: __import__('integrations.discord')))

# Category 34: Smart Environment
results.append(test("automation.smart_home", lambda: __import__('automation.smart_home')))

# Category 35: Advanced AI Model System
results.append(test("jarvis_core.ollama_service", lambda: __import__('jarvis_core.ollama_service')))
results.append(test("jarvis_core.capability_registry", lambda: __import__('jarvis_core.capability_registry')))

# Category 36: Developer Maintenance
results.append(test("updater.health_checker", lambda: __import__('updater.health_checker')))
results.append(test("updater.update_checker", lambda: __import__('updater.update_checker')))
results.append(test("updater.installer", lambda: __import__('updater.installer')))
results.append(test("diagnostics.manager", lambda: __import__('diagnostics.manager')))

# Category 37: Goals & Missions
results.append(test("goals.manager", lambda: __import__('goals.manager')))
results.append(test("missions.manager", lambda: __import__('missions.manager')))
results.append(test("brains_v2.goal_manager.base", lambda: __import__('brains_v2.goal_manager.base')))

# Category 38: Workflow Automation
results.append(test("workflow_engine", lambda: __import__('workflow_engine')))
results.append(test("brains_v2.planner.engine", lambda: __import__('brains_v2.planner.engine')))

# Category 39: Observability & Diagnostics
results.append(test("jarvis_core.observability", lambda: __import__('jarvis_core.observability')))
results.append(test("jarvis_core.diagnostics", lambda: __import__('jarvis_core.diagnostics')))

# Category 40: Self-Learning
results.append(test("brains_v2.learning.engine", lambda: __import__('brains_v2.learning.engine')))

# Category 41: AGI Engine
results.append(test("agi.engine", lambda: __import__('agi.engine')))
results.append(test("reasoning.manager", lambda: __import__('reasoning.manager')))
results.append(test("thinking.manager", lambda: __import__('thinking.manager')))

# Category 42: Final Jarvis Intelligence
results.append(test("brains_v2.manager", lambda: __import__('brains_v2.manager')))
results.append(test("brains_v2.core_bridge", lambda: __import__('brains_v2.core_bridge')))
results.append(test("jarvis", lambda: __import__('jarvis')))

# Print results
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"\n{'='*60}")
print(f"IMPORT AUDIT: {passed}/{len(results)} PASSED")
print(f"{'='*60}")
for i, (name, status, err) in enumerate(results):
    icon = "PASS" if status == "PASS" else "FAIL"
    detail = f" -- {err}" if err else ""
    print(f"  [{icon:4s}] {name}{detail}")
print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)}")
if failed > 0:
    print("\nFailed modules:")
    for name, status, err in results:
        if status == "FAIL":
            print(f"  - {name}: {err}")
