import json,urllib.request,urllib.error
from .base import IntegrationResult
def request(method,url,headers=None,payload=None,timeout=15):
 body=None if payload is None else json.dumps(payload).encode()
 req=urllib.request.Request(url,data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:
   raw=r.read().decode('utf-8','ignore');return IntegrationResult(True,json.loads(raw) if raw else {},environment_ready=True)
 except urllib.error.HTTPError as e:return IntegrationResult(False,error=f'HTTP {e.code}: '+e.read().decode('utf-8','ignore')[:300],environment_ready=True)
 except Exception as e:return IntegrationResult(False,error=f'{type(e).__name__}: {e}',environment_ready=False)
