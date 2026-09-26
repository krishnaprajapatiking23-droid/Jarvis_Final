import subprocess
from security.policy_engine import policy
class Power:
 def _run(self,action,args):
  d=policy.check('system.'+action,{'target':'local system'})
  if not d.allowed:return {'success':False,'message':d.reason,'confirmation_required':d.needs_confirmation}
  try:subprocess.run(args,check=True,timeout=10);return {'success':True,'message':action+' requested'}
  except Exception as e:return {'success':False,'message':f'{type(e).__name__}: {e}'}
 def shutdown(self):return self._run('shutdown',['shutdown','/s','/t','0'])
 def restart(self):return self._run('restart',['shutdown','/r','/t','0'])
 def sleep(self):return self._run('sleep',['rundll32.exe','powrprof.dll,SetSuspendState','0,1,0'])
 def hibernate(self):return self._run('sleep',['shutdown','/h'])
 def logout(self):return self._run('logout',['shutdown','/l'])
 def cancel_shutdown(self):return self._run('shutdown',['shutdown','/a'])
 def execute(self,command):
  low=str(command).lower()
  for name in ('shutdown','restart','hibernate','logout','sleep'):
   if name in low:return getattr(self,name)()
  return {'success':False,'message':'unsupported power action'}
power=Power()
