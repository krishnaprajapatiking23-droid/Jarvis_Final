from __future__ import annotations
import math,re,time,uuid
from core.atomic_json import AtomicJSONStore
class AGIMemory:
 def __init__(self,path='data/agi_knowledge.json'):self.store=AtomicJSONStore(path,[])
 def learn(self,kind,concept,content,domain='general',confidence=.5,source='experience',verified=False,relations=None):
  if kind not in {'experience','fact','lesson','strategy','skill','failure','preference'}:raise ValueError('invalid knowledge kind')
  item={'id':uuid.uuid4().hex[:12],'kind':kind,'concept':concept,'content':content,'domain':domain,'confidence':max(0,min(1,float(confidence))),'source':source,'verified':bool(verified),'relations':relations or [],'created':time.time(),'uses':0,'successes':0}
  def add(rows):
   for x in rows:
    if x.get('kind')==kind and x.get('concept')==concept and x.get('content')==content:return rows
   return rows+[item]
  self.store.update(add);return item
 def retrieve(self,query,domain=None,kinds=None,limit=8):
  terms=set(re.findall(r'[a-z0-9]+',query.lower()))
  out=[]
  for x in self.store.load():
   if not isinstance(x,dict):continue
   if kinds and x.get('kind') not in kinds:continue
   words=set(re.findall(r'[a-z0-9]+',(str(x.get('concept',''))+' '+str(x.get('content',''))).lower()));overlap=len(terms&words)/max(1,len(terms|words));transfer=.15 if domain and x.get('domain')!=domain and x.get('kind') in ('strategy','lesson') else 0;score=.6*overlap+.3*float(x.get('confidence',0))+transfer
   if score>0:out.append((score,x))
  return [dict(x,relevance=round(s,3)) for s,x in sorted(out,key=lambda z:z[0],reverse=True)[:limit]]
 def record_outcome(self,item_id,success):
  def f(rows):
   for x in rows:
    if x.get('id')==item_id:x['uses']=x.get('uses',0)+1;x['successes']=x.get('successes',0)+int(success);x['confidence']=round((x['confidence']+int(success))/2,3)
   return rows
  self.store.update(f)
memory=AGIMemory()
