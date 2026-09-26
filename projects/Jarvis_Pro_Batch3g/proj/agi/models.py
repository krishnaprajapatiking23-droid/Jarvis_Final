from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any
import time,uuid
@dataclass
class Evidence: source:str;claim:str;supports:bool=True;confidence:float=.5;verified:bool=False
@dataclass
class CausalLink: cause:str;effect:str;condition:str='';kind:str='possible';confidence:float=.5;evidence:list[Evidence]=field(default_factory=list)
@dataclass
class Hypothesis: statement:str;confidence:float=.5;status:str='untested';evidence:list[Evidence]=field(default_factory=list);tests:list[str]=field(default_factory=list)
@dataclass
class Experiment: hypothesis:str;action:str;prediction:str;metric:str;threshold:float|None=None;actual:Any=None;conclusion:str=''
@dataclass
class Strategy: name:str;steps:list[str];domains:list[str];constraints:list[str]=field(default_factory=list);score:float=.5;validated:bool=False
@dataclass
class TaskState: request:str;goal:str;domain:str;constraints:list[str];unknowns:list[str];plan:list[str];id:str=field(default_factory=lambda:uuid.uuid4().hex[:12]);status:str='ready';step:int=0;errors:list[str]=field(default_factory=list);observations:list[Any]=field(default_factory=list);started:float=field(default_factory=time.time)
