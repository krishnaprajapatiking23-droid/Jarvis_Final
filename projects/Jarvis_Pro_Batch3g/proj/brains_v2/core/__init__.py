from brains_v2.core.pipeline import pipeline
from brains_v2.ai.decision import decision_step

pipeline.add(decision_step)

from brains_v2.services.memory_service import memory_service

pipeline.add(memory_service.process)

from brains_v2.services.automation_service import automation_service

pipeline.add(automation_service.process)

from brains_v2.services.llm_service import llm_service

pipeline.add(llm_service.process)