from __future__ import annotations
from dataclasses import dataclass
from typing import Callable,Any
from tools.registry import Tool,ToolRegistry
@dataclass
class SkillCandidate:name:str;description:str;inputs:dict;outputs:dict;permissions:tuple;risk_level:str;dependencies:tuple;procedure:list[str];handler:Callable[...,Any];validated:bool=False
class SkillAcquirer:
 def __init__(self,registry:ToolRegistry):self.registry=registry
 def extract(self,name,description,procedure,handler,inputs=None,outputs=None,permissions=(),risk_level='medium',dependencies=()):
  if not procedure or not callable(handler):raise ValueError('repeatable procedure and handler required')
  return SkillCandidate(name,description,inputs or {},outputs or {},tuple(permissions),risk_level,tuple(dependencies),list(procedure),handler)
 def validate(self,candidate,cases):
  if not cases:return False
  for args,expected in cases:
   try:actual=candidate.handler(**args)
   except Exception:return False
   if expected is not None and actual!=expected:return False
  candidate.validated=True;return True
 def register(self,candidate):
  if not candidate.validated:raise PermissionError('unvalidated skill')
  if candidate.risk_level in ('high','critical'):raise PermissionError('high-risk generated skills require explicit human review')
  return self.registry.register_tool(candidate.name,candidate.handler,description=candidate.description,parameters=candidate.inputs,category='learned_skill',risk_level=candidate.risk_level,permissions=candidate.permissions)
