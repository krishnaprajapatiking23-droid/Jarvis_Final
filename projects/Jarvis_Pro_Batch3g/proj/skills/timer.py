from __future__ import annotations
import re,threading,time,uuid
class TimerService:
 def __init__(self,clock=time.monotonic):self.clock=clock;self.lock=threading.RLock();self.items={};self.events=[]
 def start(self,seconds,name=None,callback=None):
  if seconds<=0:raise ValueError('positive duration required')
  ident=name or uuid.uuid4().hex[:8]
  with self.lock:
   if ident in self.items and self.items[ident]['state'] in ('running','paused'):raise KeyError('timer already active')
   x={'remaining':float(seconds),'deadline':self.clock()+seconds,'state':'running','cancel':threading.Event(),'wake':threading.Event(),'callback':callback};self.items[ident]=x
  def worker():
   while True:
    with self.lock:
     state=x['state'];wait=max(0,x['deadline']-self.clock()) if state=='running' else None
    if state in ('cancelled','completed'):return
    if state=='paused':x['wake'].wait(.1);x['wake'].clear();continue
    if x['cancel'].wait(wait):return
    with self.lock:
     if x['state']!='running':continue
     x['state']='completed';x['remaining']=0;self.events.append({'type':'timer.completed','id':ident,'at':time.time()})
    if callback:callback(ident)
    return
  x['thread']=threading.Thread(target=worker,name='timer-'+ident,daemon=True);x['thread'].start();return ident
 def cancel(self,ident):
  with self.lock:
   x=self.items.get(ident)
   if not x or x['state'] in ('cancelled','completed'):return False
   x['state']='cancelled';x['cancel'].set();x['wake'].set();return True
 def pause(self,ident):
  with self.lock:
   x=self.items.get(ident)
   if not x or x['state']!='running':return False
   x['remaining']=max(0,x['deadline']-self.clock());x['state']='paused';x['wake'].set();return True
 def resume(self,ident):
  with self.lock:
   x=self.items.get(ident)
   if not x or x['state']!='paused':return False
   x['deadline']=self.clock()+x['remaining'];x['state']='running';x['wake'].set();return True
 def remaining(self,ident):
  with self.lock:
   x=self.items.get(ident)
   if not x:return None
   return max(0,x['deadline']-self.clock()) if x['state']=='running' else x['remaining']
 def status(self):
  with self.lock:return {k:{'state':v['state'],'remaining':self.remaining(k)} for k,v in self.items.items()}
timers=TimerService()
def _id(t):
 m=re.search(r'timer\s+([\w-]+)',t);return m.group(1) if m and not m.group(1).isdigit() else None
def process_timer(command):
 t=str(command or '').lower()
 if 'timer' not in t:return None
 ident=_id(t);active=[k for k,v in timers.status().items() if v['state'] in ('running','paused')];ident=ident or (active[-1] if active else None)
 if 'cancel' in t:return 'Timer cancelled.' if ident and timers.cancel(ident) else 'No active timer.'
 if 'pause' in t:return 'Timer paused.' if ident and timers.pause(ident) else 'No running timer.'
 if 'resume' in t:return 'Timer resumed.' if ident and timers.resume(ident) else 'No paused timer.'
 if 'remaining' in t or 'status' in t:
  s=timers.status();return 'No timers.' if not s else '; '.join(f"{k}: {v['state']} {v['remaining']:.1f}s" for k,v in s.items())
 m=re.search(r'(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?)',t)
 if not m:return 'Please provide a timer duration.'
 seconds=float(m.group(1))*(3600 if m.group(2).startswith('hour') else 60 if m.group(2).startswith('minute') else 1);ident=timers.start(seconds);return f'Timer {ident} started for {seconds:g}s.'
