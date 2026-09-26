from __future__ import annotations
from .models import Strategy
class LearningPipeline:
 def __init__(self,memory):self.memory=memory
 def learn_experience(self,goal,strategy,result,evaluation,domain):
  if not evaluation.get('verified') or evaluation.get('score',0)<.7:return None
  lesson=evaluation.get('lesson') or f'{strategy.name} worked for {goal}'
  return self.memory.learn('strategy',strategy.name,lesson,domain,min(1,evaluation['score']),source='evaluated experience',verified=True,relations=[{'goal':goal,'result':str(result)[:300]}])
 def transfer(self,problem,domain):return self.memory.retrieve(problem,domain,kinds={'strategy','lesson'},limit=5)
learning=None
