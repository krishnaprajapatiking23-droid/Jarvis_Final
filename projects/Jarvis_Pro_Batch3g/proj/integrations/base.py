from dataclasses import dataclass
from typing import Any
@dataclass
class IntegrationResult:ok:bool;data:Any=None;error:str='';environment_ready:bool=False
class IntegrationError(RuntimeError):pass
