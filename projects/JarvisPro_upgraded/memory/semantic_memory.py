from __future__ import annotations
import logging,math
from difflib import SequenceMatcher
from core.atomic_json import AtomicJSONStore
log=logging.getLogger('jarvis.semantic_memory')
class SemanticMemory:
 def __init__(self,file_path='data/semantic_memory.json'):self.store=AtomicJSONStore(file_path,[]);self.file_path=file_path
 def load(self):return self.store.load()
 def save(self,rows):return self.store.save(rows)
 def add(self,topic,content,tags=None,vector=None,kind='fact',confidence=.7):
  item={'topic':str(topic),'content':str(content),'tags':[str(x) for x in tags or []],'kind':kind,'confidence':float(confidence)}
  if vector is not None:
   if not isinstance(vector,list) or not vector or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vector):raise ValueError('invalid vector')
   item['vector']=vector
  self.store.update(lambda r:r+[item]);return True
 store=add
 def similarity(self,a,b):return SequenceMatcher(None,str(a).lower(),str(b).lower()).ratio()
 def search(self,query,threshold=.6,vector=None):
  rows=self.load()
  if not rows:return []
  if vector is not None and (not isinstance(vector,list) or not vector):raise ValueError('invalid query vector')
  out=[]
  for i,m in enumerate(rows):
   if not isinstance(m,dict) or not isinstance(m.get('topic'),str) or not isinstance(m.get('content'),str):log.warning('skipping corrupt memory entry %s',i);continue
   if vector is not None and 'vector' in m:
    v=m['vector']
    if not isinstance(v,list) or len(v)!=len(vector):log.warning('vector dimension mismatch at %s',i);continue
    den=(sum(x*x for x in v)*sum(x*x for x in vector))**.5;score=sum(a*b for a,b in zip(v,vector))/den if den else 0
   else:score=max([self.similarity(query,m['topic']),self.similarity(query,m['content'])]+[self.similarity(query,t) for t in m.get('tags',[]) if isinstance(t,str)])
   if score>=threshold:out.append({'score':round(score,4),'memory':m})
  return sorted(out,key=lambda x:x['score'],reverse=True)
 def delete(self,topic):
  old=self.load();new=[m for m in old if str(m.get('topic','')).lower()!=str(topic).lower()];self.save(new);return len(new)!=len(old)
 def all(self):return self.load()
semantic_memory=SemanticMemory()
