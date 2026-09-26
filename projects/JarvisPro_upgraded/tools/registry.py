from __future__ import annotations
import importlib,inspect,logging,threading
from dataclasses import dataclass,field
from typing import Any,Callable
from security.policy_engine import policy
log=logging.getLogger('jarvis.tools')
@dataclass
class Tool:name:str;description:str;parameters:dict;handler:Callable[...,Any];category:str='general';risk_level:str='low';enabled:bool=True;permissions:tuple[str,...]=field(default_factory=tuple)
class ToolRegistry:
 def __init__(self):self._lock=threading.RLock();self._tools={};self._bootstrapped=False;self.errors=[]
 def register_tool(self,name,handler=None,**meta):
  tool=name if isinstance(name,Tool) else Tool(str(name),meta.pop('description',inspect.getdoc(handler) or ''),meta.pop('parameters',{}),handler,**meta)
  if not tool.name.strip() or not callable(tool.handler):raise TypeError('valid name and callable handler required')
  with self._lock:
   if tool.name in self._tools:raise KeyError(f'duplicate tool: {tool.name}')
   self._tools[tool.name]=tool
  return tool
 def unregister_tool(self,name):
  with self._lock:return self._tools.pop(name,None)
 def get_tool(self,name):
  with self._lock:return self._tools.get(name)
 def has_tool(self,name):return self.get_tool(name) is not None
 exists=has_tool
 def list_tools(self):
  with self._lock:return list(self._tools.values())
 def enable_tool(self,name):
  t=self.get_tool(name)
  if not t:raise KeyError(name)
  t.enabled=True;return t
 def disable_tool(self,name):
  t=self.get_tool(name)
  if not t:raise KeyError(name)
  t.enabled=False;return t
 def execute_tool(self,name,*args,**kwargs):
  t=self.get_tool(name)
  if not t:raise KeyError(f'unknown tool: {name}')
  if not t.enabled:raise PermissionError(f'disabled tool: {name}')
  action={'low':'read','medium':'file.write','high':'code.execute','critical':'system.shutdown'}.get(t.risk_level,t.risk_level)
  d=policy.check(action,{'tool':name,'category':t.category})
  if not d.allowed:raise PermissionError(d.reason)
  return t.handler(*args,**kwargs)
 def bootstrap(self):
  with self._lock:
   if self._bootstrapped:return len(self._tools)
   self._bootstrapped=True
  specs=[('stopwatch','skills.stopwatch','process_stopwatch','time','low'),('timer','skills.timer','process_timer','time','low'),('reminder','brains_v2.manager_modules.reminder_manager','process','productivity','medium'),('open_app','automation.apps','open_app','automation','low'),('open_website','automation.browser','open_website','browser','low'),('google_workspace','integrations.tools','google_tool','integration','low'),('github','integrations.tools','github_tool','integration','low'),('whatsapp','integrations.tools','whatsapp_tool','messaging','medium'),('smart_home','integrations.tools','smart_home_tool','iot','medium')]
  for name,module,attr,category,risk in specs:
   try:
    fn=getattr(importlib.import_module(module),attr)
    if not self.has_tool(name):self.register_tool(name,fn,description=inspect.getdoc(fn) or name,category=category,risk_level=risk)
   except Exception as e:self.errors.append({'tool':name,'error':f'{type(e).__name__}: {e}'});log.error('failed to register %s: %s',name,e)
  log.info('Tool Registry loaded: %d tools registered; %d failed',len(self._tools),len(self.errors));return len(self._tools)
registry=ToolRegistry();TOOLS=registry._tools
register_tool=registry.register_tool;unregister_tool=registry.unregister_tool;get_tool=registry.get_tool;has_tool=registry.has_tool;list_tools=registry.list_tools;execute_tool=registry.execute_tool;enable_tool=registry.enable_tool;disable_tool=registry.disable_tool
