from __future__ import annotations
import copy,re
from .models import CausalLink,Evidence,Hypothesis,Experiment,Strategy
class ReasoningEngine:
 def domain(self,text):
  scores={d:sum(w in text.lower() for w in words) for d,words in {'coding':['code','python','bug','test'],'troubleshooting':['slow','crash','fail','error'],'automation':['automate','file','window','click'],'research':['research','source','evidence'],'planning':['plan','schedule','goal'],'business':['cost','customer','revenue']}.items()};return max(scores,key=scores.get) if max(scores.values()) else 'general'
 def causal_chain(self,links,start):
  chain=[];seen=set();current=start
  while current not in seen:
   seen.add(current);matches=[x for x in links if x.cause==current]
   if not matches:break
   best=max(matches,key=lambda x:x.confidence);chain.append(best);current=best.effect
  return chain
 def update_cause(self,link,evidence):
  link.evidence.append(evidence);support=sum((1 if e.supports else -1)*e.confidence for e in link.evidence);link.confidence=max(0,min(1,.5+support/max(1,len(link.evidence))/2));link.kind='verified' if link.confidence>=.8 and any(e.verified for e in link.evidence) else 'possible';return link
 def analogize(self,current,experiences):
  structure=set(re.findall(r'[a-z]+',current.lower()))&{'connection','dependency','timeout','invalid','missing','slow','failure','permission','resource'}
  ranked=[]
  for x in experiences:
   old=set(re.findall(r'[a-z]+',(x.get('concept','')+' '+x.get('content','')).lower()));shared=structure&old
   if shared:ranked.append({'source':x,'shared_structure':sorted(shared),'adapted_strategy':x.get('content'),'score':len(shared)/len(structure or {1})})
  return sorted(ranked,key=lambda x:x['score'],reverse=True)
 def counterfactual(self,state,changes,rules):
  hypothetical=copy.deepcopy(state);hypothetical.update(copy.deepcopy(changes));effects=[]
  for rule in rules:
   if all(hypothetical.get(k)==v for k,v in rule.get('if',{}).items()):hypothetical.update(rule.get('then',{}));effects.append(rule.get('description',str(rule.get('then'))))
  return {'actual':copy.deepcopy(state),'hypothetical':hypothetical,'changes':copy.deepcopy(changes),'effects':effects}
 def hypotheses(self,problem):
  t=problem.lower();base=[]
  if any(x in t for x in ('slow','latency')):base=[('CPU/resource bottleneck','measure CPU utilization'),('database bottleneck','measure query time'),('network dependency','measure network latency')]
  elif any(x in t for x in ('crash','error','fail')):base=[('missing dependency','verify imports/packages'),('invalid configuration','validate configuration'),('runtime exception','capture traceback')]
  else:base=[('missing information','gather required facts'),('constraint conflict','validate constraints'),('tool unavailable','check capabilities')]
  return [Hypothesis(s,.6-i*.1,tests=[test]) for i,(s,test) in enumerate(base)]
 def evaluate_hypothesis(self,h,evidence):
  h.evidence.extend(evidence);delta=sum((1 if e.supports else -1)*e.confidence for e in evidence)/max(1,len(evidence));h.confidence=max(0,min(1,h.confidence+delta*.35));h.status='supported' if h.confidence>=.75 else 'rejected' if h.confidence<=.25 else 'uncertain';return h
 def plan_experiment(self,h,metric='result',threshold=None):return Experiment(h.statement,h.tests[0] if h.tests else 'collect evidence',f'evidence will support: {h.statement}',metric,threshold)
 def conclude_experiment(self,e,actual,supports):e.actual=actual;e.conclusion='supported' if supports else 'not supported';return e
reasoner=ReasoningEngine()
