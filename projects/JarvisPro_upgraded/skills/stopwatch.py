from __future__ import annotations
import threading,time
class Stopwatch:
 def __init__(self,clock=time.monotonic):self.clock=clock;self.lock=threading.RLock();self.reset()
 def reset(self):
  with self.lock:self.acc=0.;self.started=None;self.state='reset';return 0.
 def start(self):
  with self.lock:
   if self.state=='running':return self.elapsed()
   if self.state in ('reset','stopped'):self.acc=0.
   self.started=self.clock();self.state='running';return self.acc
 def pause(self):
  with self.lock:
   if self.state!='running':raise RuntimeError('not running')
   self.acc+=self.clock()-self.started;self.started=None;self.state='paused';return self.acc
 def resume(self):
  with self.lock:
   if self.state!='paused':raise RuntimeError('not paused')
   self.started=self.clock();self.state='running';return self.acc
 def stop(self):
  with self.lock:
   if self.state=='running':self.acc+=self.clock()-self.started
   self.started=None;self.state='stopped';return self.acc
 def elapsed(self):
  with self.lock:return self.acc+(self.clock()-self.started if self.state=='running' else 0.)
stopwatch=Stopwatch()
def process_stopwatch(command):
 t=str(command or '').lower()
 if 'stopwatch' not in t:return None
 try:
  if 'pause' in t:return f'Stopwatch paused at {stopwatch.pause():.2f}s.'
  if 'resume' in t:stopwatch.resume();return 'Stopwatch resumed.'
  if 'reset' in t:stopwatch.reset();return 'Stopwatch reset.'
  action=t.replace('stopwatch',' ').strip().split()
  verb=action[0] if action else 'status'
  if verb=='stop':return f'Stopwatch stopped at {stopwatch.stop():.2f}s.'
  if verb=='start':stopwatch.start();return 'Stopwatch started.'
  return f'Stopwatch {stopwatch.state}: {stopwatch.elapsed():.2f}s.'
 except RuntimeError as e:return f'Stopwatch error: {e}.'
