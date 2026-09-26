from __future__ import annotations
import ast,os,subprocess,sys,tempfile
from dataclasses import dataclass
@dataclass
class SandboxResult:ok:bool;stdout:str='';stderr:str='';returncode:int|None=None;timed_out:bool=False;isolation:str='process+rlimits'
FORBIDDEN={'ctypes','multiprocessing','socket','subprocess'}
def validate(code):
 tree=ast.parse(code)
 for n in ast.walk(tree):
  if isinstance(n,(ast.Import,ast.ImportFrom)):
   names=[x.name.split('.')[0] for x in n.names] if isinstance(n,ast.Import) else [str(n.module or '').split('.')[0]]
   if any(x in FORBIDDEN for x in names):raise PermissionError('forbidden module')
 return tree
def run_python(code,timeout=3,memory_mb=128):
 validate(code)
 with tempfile.TemporaryDirectory(prefix='jarvis-sandbox-') as d:
  p=os.path.join(d,'task.py')
  with open(p,'w',encoding='utf-8') as source:
   source.write(code)
  pre=None
  if os.name=='posix':
   def limits():
    import resource;resource.setrlimit(resource.RLIMIT_CPU,(max(1,int(timeout)),max(1,int(timeout)+1)));resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024**2,memory_mb*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2));resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
   pre=limits
  env={'PATH':os.environ.get('PATH',''),'PYTHONIOENCODING':'utf-8'}
  try:
   x=subprocess.run([sys.executable,'-I',p],cwd=d,env=env,text=True,capture_output=True,timeout=timeout,preexec_fn=pre)
   return SandboxResult(x.returncode==0,x.stdout[:10000],x.stderr[:10000],x.returncode,False)
  except subprocess.TimeoutExpired as e:return SandboxResult(False,(e.stdout or '')[:10000] if isinstance(e.stdout,str) else '',(e.stderr or '')[:10000] if isinstance(e.stderr,str) else 'timeout',None,True)
