from __future__ import annotations
import re,time
from .models import TaskState,Strategy
from .memory import AGIMemory,memory
from .reasoning import ReasoningEngine,reasoner
from .learning import LearningPipeline
class AGIEngine:
 def __init__(self,memory_=memory,reasoner_=reasoner):self.memory=memory_;self.reasoner=reasoner_;self.learning=LearningPipeline(memory_);self.last=None
 def understand(self,request):
  domain=self.reasoner.domain(request);constraints=[x for x in ('offline','limited memory','no network','deadline','budget','permission') if x in request.lower()];unknowns=[] if len(request.split())>3 else ['insufficient detail'];templates={'coding':['clarify requirements','inspect environment','design','implement','test','correct','verify'],'troubleshooting':['collect symptoms','generate hypotheses','rank tests','run tests','evaluate evidence','apply safe fix','verify'],'research':['define question','collect sources','validate evidence','synthesize','verify'],'general':['define goal','retrieve knowledge','compare strategies','execute','evaluate','correct','verify']};return TaskState(request,request.strip(),domain,constraints,unknowns,templates.get(domain,templates['general']))
 def discover_strategies(self,state,known,failures):
  base=[Strategy('decompose-verify',['split goal','execute dependencies','verify each output'],[state.domain]),Strategy('hypothesis-first',['generate hypotheses','test cheapest first','update confidence'],[state.domain])]
  if failures:base.append(Strategy('failure-derived alternative',['classify failure','remove failed assumption','select different tool or sequence','verify'],[state.domain]))
  return [s for s in base if s.name not in {x.get('concept') for x in known}]
 def explore(self,gap,search,limit=3,seconds=5):
  started=time.monotonic();evidence=[]
  for query in [gap,f'{gap} evidence',f'{gap} alternatives'][:max(0,min(limit,5))]:
   if time.monotonic()-started>seconds:break
   result=search(query) or []
   for x in result:
    if isinstance(x,dict) and x.get('source') and x.get('claim'):evidence.append(x)
  return evidence
 def acquire_knowledge(self,evidence,minimum_sources=2):
  grouped={}
  for e in evidence:grouped.setdefault(e['claim'],set()).add(e['source'])
  learned=[]
  for claim,sources in grouped.items():learned.append(self.memory.learn('fact',claim,claim,source=', '.join(sorted(sources)),confidence=min(.95,.45+.2*len(sources)),verified=len(sources)>=minimum_sources))
  return learned
 def run(self,request,executor,max_attempts=3,timeout=30):
  state=self.understand(request);known=self.learning.transfer(request,state.domain);strategies=self.discover_strategies(state,known,[]);started=time.monotonic();attempts=[]
  for strategy in strategies[:max_attempts]:
   if time.monotonic()-started>timeout:state.status='timeout';break
   try:
    result=executor(state,strategy);verified=bool(result.get('verified')) if isinstance(result,dict) else result is not None;attempts.append({'strategy':strategy.name,'result':result,'verified':verified})
    if verified:
     state.status='completed';self.learning.learn_experience(state.goal,strategy,result,{'verified':True,'score':.9,'lesson':f'Use {strategy.name} for {state.domain} tasks after checking constraints'},state.domain);self.last={'state':state,'attempts':attempts,'memory':known};return self.last
    state.errors.append('verification failed')
   except Exception as e:state.errors.append(f'{type(e).__name__}: {e}');attempts.append({'strategy':strategy.name,'error':state.errors[-1]})
   strategies.extend(self.discover_strategies(state,known,state.errors))
  state.status='failed';self.last={'state':state,'attempts':attempts,'memory':known};return self.last
engine=AGIEngine()
