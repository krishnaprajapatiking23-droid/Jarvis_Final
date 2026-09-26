from __future__ import annotations
import copy,json,logging,os,tempfile,threading
from pathlib import Path
_LOCKS={};_MASTER=threading.Lock();log=logging.getLogger('jarvis.storage')
def _lock(p):
 k=str(p.resolve())
 with _MASTER:return _LOCKS.setdefault(k,threading.RLock())
class AtomicJSONStore:
 def __init__(self,path,default):self.path=Path(path);self.default=default;self.lock=_lock(self.path)
 def load(self):
  with self.lock:
   if not self.path.exists():return copy.deepcopy(self.default)
   try:
    data=json.loads(self.path.read_text(encoding='utf-8'))
    if not isinstance(data,type(self.default)):raise ValueError(f'expected {type(self.default).__name__}')
    return data
   except (OSError,json.JSONDecodeError,ValueError) as e:log.error('corrupt JSON %s: %s',self.path,e);return copy.deepcopy(self.default)
 def save(self,data):
  with self.lock:
   self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix='.'+self.path.name,suffix='.tmp')
   try:
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,default=str);f.flush();os.fsync(f.fileno())
    os.replace(tmp,self.path)
   finally:
    try:os.unlink(tmp)
    except FileNotFoundError:pass
  return data
 def update(self,fn):
  with self.lock:data=self.load();new=fn(data);return self.save(data if new is None else new)
