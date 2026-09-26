from __future__ import annotations
import hashlib,hmac,os,secrets,threading,time
class AuthManager:
 def __init__(self,ttl=3600,clock=time.time,require_pairing=False):self.ttl=ttl;self.clock=clock;self.require_pairing=require_pairing;self.lock=threading.RLock();self.tokens={}
 def _hash(self,t):return hashlib.sha256(t.encode()).hexdigest()
 def create_token(self,device='Unknown',scopes=('command:read',),pairing_secret=None):
  expected=os.getenv('JARVIS_PAIRING_SECRET','')
  if self.require_pairing and not expected:raise PermissionError('server pairing is disabled until JARVIS_PAIRING_SECRET is configured')
  if expected and not hmac.compare_digest(str(pairing_secret or ''),expected):raise PermissionError('invalid pairing secret')
  allowed={'command:read','command:execute'};requested=set(scopes)
  if not requested<=allowed:raise PermissionError('unsupported scope requested')
  token=secrets.token_urlsafe(32)
  with self.lock:self.tokens[self._hash(token)]={'device':str(device)[:100],'scopes':tuple(sorted(requested)),'expires':self.clock()+self.ttl}
  return token
 def verify(self,token,scope=None):
  key=self._hash(str(token or ''))
  with self.lock:
   x=self.tokens.get(key)
   if not x:return False
   if x['expires']<=self.clock():self.tokens.pop(key,None);return False
   return scope is None or scope in x['scopes']
 def remove(self,token):
  with self.lock:return self.tokens.pop(self._hash(str(token or '')),None) is not None
 def get_device(self,token):
  key=self._hash(str(token or ''))
  with self.lock:x=self.tokens.get(key)
  return x['device'] if x and self.verify(token) else None
auth=AuthManager(require_pairing=True)
