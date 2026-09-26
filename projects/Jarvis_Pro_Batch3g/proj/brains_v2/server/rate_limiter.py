import threading,time
class RateLimiter:
 def __init__(self,limit=30,window=60,clock=time.monotonic):self.limit=limit;self.window=window;self.clock=clock;self.lock=threading.RLock();self.hits={}
 def allow(self,key):
  now=self.clock()
  with self.lock:
   rows=[x for x in self.hits.get(key,[]) if now-x<self.window]
   if len(rows)>=self.limit:self.hits[key]=rows;return False
   rows.append(now);self.hits[key]=rows;return True
limiter=RateLimiter()
