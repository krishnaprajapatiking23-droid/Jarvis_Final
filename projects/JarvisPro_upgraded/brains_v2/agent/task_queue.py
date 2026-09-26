from __future__ import annotations
import heapq,itertools,threading,time,uuid
from dataclasses import dataclass,field
from typing import Any,Callable
HIGH=1;NORMAL=2;LOW=3;PENDING='pending';RUNNING='running';CANCELLING='cancelling';DONE='done';FAILED='failed';CANCELLED='cancelled';PRIORITY_NAMES={1:'high',2:'normal',3:'low'}
@dataclass
class Task:
 id:str;description:str;handler:Callable[...,Any];priority:int=NORMAL;status:str=PENDING;background:bool=True;parent_id:str|None=None;children:set[str]=field(default_factory=set);cancel_flag:threading.Event=field(default_factory=threading.Event);created_at:float=field(default_factory=time.time);started_at:float=0.;finished_at:float=0.;result:Any=None;error:str='';progress:str=''
 @property
 def cancelled(self):return self.cancel_flag.is_set()
 @property
 def duration(self):return round((self.finished_at or time.time())-self.started_at,3) if self.started_at else 0
 def report(self):return {'id':self.id,'description':self.description,'status':self.status,'parent_id':self.parent_id,'children':sorted(self.children),'result':self.result if self.status==DONE else None,'error':self.error,'duration':self.duration}
class TaskQueue:
 def __init__(self,max_concurrent=1):self.max_concurrent=max(1,int(max_concurrent));self.lock=threading.RLock();self.wake=threading.Event();self.stop_event=threading.Event();self.heap=[];self.tasks={};self.counter=itertools.count();self.workers=[]
 def submit(self,description,handler,priority=NORMAL,background=True,parent_id=None):
  t=Task(id=uuid.uuid4().hex[:10],description=description,handler=handler,priority=priority,background=background,parent_id=parent_id)
  with self.lock:
   if parent_id:
    p=self.tasks.get(parent_id)
    if not p:raise KeyError('parent task not found')
    if p.cancelled:raise RuntimeError('parent already cancelled')
    p.children.add(t.id)
   self.tasks[t.id]=t;heapq.heappush(self.heap,(priority,next(self.counter),t.id))
  self.start();self.wake.set();return t.id
 def start(self):
  with self.lock:
   self.workers=[w for w in self.workers if w.is_alive()];self.stop_event.clear()
   while len(self.workers)<self.max_concurrent:
    w=threading.Thread(target=self._loop,daemon=True,name=f'jarvis-task-{len(self.workers)}');self.workers.append(w);w.start()
 def _next(self):
  with self.lock:
   while self.heap:
    _,_,i=heapq.heappop(self.heap);t=self.tasks.get(i)
    if t and t.status==PENDING and not t.cancelled:return t
    if t and t.cancelled:t.status=CANCELLED;t.finished_at=time.time()
  return None
 def _loop(self):
  while not self.stop_event.is_set():
   t=self._next()
   if not t:self.wake.wait(.05);self.wake.clear();continue
   self._execute(t)
 def _execute(self,t):
  t.status=RUNNING;t.started_at=time.time()
  try:
   if t.cancelled:raise InterruptedError()
   try:r=t.handler(task=t)
   except TypeError:r=t.handler()
   if t.cancelled:t.status=CANCELLED;t.error='cancelled'
   else:t.result=r;t.status=DONE
  except InterruptedError:t.status=CANCELLED;t.error='cancelled'
  except Exception as e:t.status=FAILED;t.error=f'{type(e).__name__}: {e}'
  finally:t.finished_at=time.time()
 def cancel(self,task_id):
  with self.lock:
   root=self.tasks.get(task_id)
   if not root or root.status in (DONE,FAILED,CANCELLED):return False
   stack=[task_id];seen=set()
   while stack:
    i=stack.pop()
    if i in seen:continue
    seen.add(i);t=self.tasks.get(i)
    if not t:continue
    t.status=CANCELLING if t.status==RUNNING else CANCELLED;t.cancel_flag.set();stack.extend(t.children)
    if t.status==CANCELLED:t.finished_at=time.time()
  self.wake.set();return True
 def wait(self,i,timeout=5):
  end=time.time()+timeout
  while time.time()<end:
   r=self.status(i)
   if r['status'] in (DONE,FAILED,CANCELLED):return r
   time.sleep(.02)
  return self.status(i)
 def status(self,i):
  with self.lock:t=self.tasks.get(i);return t.report() if t else {'id':i,'status':'unknown'}
 def active(self):return [t.report() for t in self.tasks.values() if t.status in (PENDING,RUNNING,CANCELLING)]
 def all_statuses(self,limit=50):return [t.report() for t in list(self.tasks.values())[-limit:]]
 def pending_count(self):return sum(t.status==PENDING for t in self.tasks.values())
 def cancel_all(self):return sum(self.cancel(i) for i in list(self.tasks))
 def shutdown(self,wait=2):
  self.cancel_all();self.stop_event.set();self.wake.set()
  for w in self.workers:w.join(wait)
  self.workers=[]
 def cleanup(self,older_than=0):
  cutoff=time.time()-older_than;ids=[i for i,t in self.tasks.items() if t.status in (DONE,FAILED,CANCELLED) and t.finished_at<=cutoff]
  for i in ids:self.tasks.pop(i,None)
  return len(ids)
 def summary(self):return {'total':len(self.tasks),'workers':sum(w.is_alive() for w in self.workers),'active':len(self.active())}
 def run_now(self,description,handler):
  t=Task(id=uuid.uuid4().hex[:10],description=description,handler=handler,priority=HIGH,background=False);self.tasks[t.id]=t;self._execute(t);return t.report()
queue=TaskQueue();get_queue=lambda:queue
