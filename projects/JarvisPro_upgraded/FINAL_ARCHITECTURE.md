# JarvisPro — Final Architecture Document

**Version:** 1.0.0  
**Canonical runtime:** `brains_v2/` (29,508 LOC · 390 files)

---

## Entry Points

```
User Input
    │
    ├── Text / Chat  →  jarvis.py  →  JarvisRuntime.start()  →  pipeline().run()
    ├── Voice         →  brains_v2/voice_v2/pipeline.py
    ├── GUI           →  gui/main.py  (7 pages, each wired to real backends)
    ├── Telegram      →  integrations/telegram.py  (urllib HTTP bot)
    ├── Discord       →  integrations/discord.py  (urllib REST bot)
    └── API           →  api/service.py
```

---

## Canonical Runtime Architecture

```
USER INPUT
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  JarvisRuntime  (brains_v2/runtime.py)                 │
│  - wires all subsystems together                        │
│  - dependency injection for testability                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BrainV2.process(command)  (brains_v2/manager.py)       │
│  - intent detection                                      │
│  - context assembly                                      │
│  - manager selection via ManagerRegistry                 │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  Pipeline stages (brains_v2/core/pipeline.py)            │
│  UNDERSTAND → INTENT → CONTEXT → MEMORY → PROFILE      │
│  → POLICY → DECISION → PLANNING → TASK → EXECUTION     │
│  → OBSERVATION → VERIFICATION → SUCCESS/FAILURE        │
│  → LEARN → EXPERIENCE → REPORT                         │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  ManagerRegistry  (jarvis_core/decisions.py)             │
│  - capability-based routing                             │
│  - fallback selection                                    │
│  - 28 capabilities probed                                │
└────────────┬────────────────────────────────────────────┘
             │
     ┌───────┴──────────────────────────────────┐
     │  MANAGERS (selected by capability match) │
     ├──────────────────────────────────────────┤
     │  automation_manager   (files, proc, KB)  │
     │  browser_manager      (Playwright)        │
     │  coding_manager       (brains_v2/coding) │
     │  research_manager     (web search)       │
     │  memory_manager       (sqlite)            │
     │  task_manager         (state machine)    │
     │  reminder_manager     (scheduler)         │
     │  notes_manager        (CRUD)              │
     │  vision_manager       (screenshot+OCR)    │
     │  voice_manager        (STT/TTS)          │
     │  mobile_manager       (ADB bridge)        │
     │  skill_manager        (plugin registry)  │
     └──────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  Execution Engine  (jarvis_core/agent_runtime.py)        │
│  - foreground / background                               │
│  - timeout / retry / pause / cancel                     │
│  - verification                                          │
│  - rollback                                              │
└─────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  Self-Correction  (brains_v2/self_correction.py)        │
│  FAILURE → capture → classify → root-cause → correct   │
│  → test → retry → verify → store → prevent repeat     │
└─────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  Learning / Experience  (brains_v2/learning/)           │
│  experience.py  - experience store with similarity      │
│  patterns.py    - pattern detection & ranking           │
│  engine.py      - learning loop (success/failure/FB)    │
└─────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  Observability  (jarvis_core/observability.py)           │
│  - trace IDs on every operation                          │
│  - structured logs                                       │
│  - health dashboard                                       │
│  - failure reports                                       │
└─────────────────────────────────────────────────────────┘
```

---

## BrainV2 Internal Subsystems

### Perception Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Voice pipeline | `brains_v2/voice_v2/pipeline.py` | STT → intent → response → TTS |
| Vision pipeline | `brains_v2/vision_v2/` | Screenshot → OCR → analysis |
| Chat input | `brains_v2/conversation.py` | Text → session → history |

### Understanding Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Intent engine | `brains_v2/ai/intent_engine.py` | Pattern + semantic intent detection |
| Context engine | `jarvis_core/decisions.py::ContextEngine` | Conflict resolution, TTL, compression |
| Personality | `jarvis_core/profile_store.py::Personality` | Emotional context, tone selection |

### Memory Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Short-term memory | `jarvis_core/memory_lifecycle.py` | Active conversation context |
| Long-term memory | `jarvis_core/memory_lifecycle.py` | SQLite-persisted facts |
| Episodic memory | `brains_v2/experience.py` | Experience records |
| Semantic memory | `jarvis_core/knowledge_graph.py` | RDF triples |
| Profile store | `jarvis_core/profile_store.py` | User preferences + skills |

### Planning Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Planner | `brains_v2/planner/` | Multi-step decomposition |
| Goal manager | `brains_v2/goal_manager/` | Goals → milestones → tasks |
| Decision tree | `brains_v2/decision_tree.py` | Branch selection |
| AGI engine | `agi/engine.py` | Bounded reasoning, analogies |

### Execution Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Agent runtime | `jarvis_core/agent_runtime.py` | Foreground/background tasks |
| Automation | `jarvis_core/automation_manager.py` | OS-level actions |
| Browser | `jarvis_core/browser_manager.py` | Web automation |
| Coding | `brains_v2/manager_modules/coding_manager.py` | Code write/read/debug |
| Research | `jarvis_core/research_manager.py` | Web search + synthesis |

### Reflection Layer
| Component | File | Responsibility |
|-----------|------|---------------|
| Self-correction | `brains_v2/self_correction.py` | Failure → correction loop |
| Self-improvement | `jarvis_core/self_improvement.py` | Safe patch + regression |
| Reflection | `brains_v2/reflection.py` | Self-evaluation |
| Analytics | `jarvis_core/analytics.py` | Performance telemetry |

### Infrastructure
| Component | File | Responsibility |
|-----------|------|---------------|
| Event bus | `jarvis_core/event_bus.py` | Cross-manager events |
| Policy engine | `jarvis_core/policy.py` | Permissions + confirmations |
| Recovery manager | `jarvis_core/recovery.py` | Corruption detection + restore |
| Backup manager | `updater/backup_manager.py` | Versioned backups |
| Health checker | `updater/health_checker.py` | Startup diagnostics |
| Observability | `jarvis_core/observability.py` | Traces + structured logs |

---

## GUI Architecture

```
gui/main.py  (7 pages)
    │
    ├── HomePage    →  psutil / platform / capability_registry
    ├── ChatPage    →  BrainV2.process() via route_command()
    ├── MemoryPage  →  get_kernel().memory
    ├── SettingsPage →  HealthChecker / UpdateChecker / BackupManager
    ├── ProjectsPage →  project_manager()
    ├── CodingPage  →  route_command() → coding_manager
    └── BusinessPage →  business_manager()

All pages share: get_kernel() for shared state
```

---

## Data Flow — Feature Connection Requirements

Every feature must have a traceable path:

```
FEATURE MODULE
    ↓
MANAGER (selected by registry)
    ↓
ROUTER (command → manager mapping)
    ↓
TASK SYSTEM (create → queue → execute)
    ↓
EXECUTION ENGINE (timeout / retry / cancel)
    ↓
VERIFICATION ENGINE (expected vs actual)
    ↓
RESULT (reply / state change)
    ↓
MEMORY / LEARNING (persist + pattern)
```

Features that exist but are NOT reachable through this chain → 🔌 NOT_CONNECTED.

---

## Legacy vs Canonical

| Path | Role |
|------|------|
| `brains_v2/` | **Canonical BrainV2** — all new development |
| `brain/` | Legacy shim → re-exports from `brains_v2.brain.*` |
| `core/` | Legacy shim → thin wrappers |
| `jarvis_core/` | Shared subsystems (kernel, automation, memory, etc.) |
| `vision/` | Legacy vision → thin adapter to `brains_v2.core_bridge` |
| `brains_v2/vision/` | Canonical vision subsystem |
| `brains_v2/voice/` | Canonical voice subsystem |

---

## Database Schema Summary

| Database | Location | Contents |
|----------|----------|----------|
| Memory | `data/memory/memory.db` | Short/long-term memories, semantic triples |
| Tasks | `data/tasks/tasks.db` | Task records with state machine |
| Reminders | `data/reminders/reminders.db` | Scheduled notifications |
| Notes | `data/notes/notes.db` | Note records with categories |
| Experience | `data/experience/experience.db` | Learning records, patterns |
| Profile | `data/profile/profile.json` | User preferences + skills |
| Analytics | `data/analytics/stats.db` | Performance telemetry |

---

## Security Boundaries

```
USER INPUT
    ↓
POLICY ENGINE  ←  owner identity / guest mode
    ↓
CAPABILITY CHECK  ←  per-task permissions
    ↓
ACTION EXECUTION  ←  tool-level verification
    ↓
RESULT VERIFICATION  ←  post-action check
    ↓
AUDIT LOG  ←  every privileged action recorded
```

Protected operations require explicit confirmation. Secrets never logged.
