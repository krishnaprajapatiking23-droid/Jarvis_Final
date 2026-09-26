import os
from dataclasses import dataclass
from security.policy_engine import policy
from .http import request
from .base import IntegrationResult
@dataclass
class Device:id:str;name:str;room:str;capabilities:tuple;state:dict
class Provider:
 def discover(self):raise NotImplementedError
 def command(self,device,action,value=None):raise NotImplementedError
 def state(self,device):raise NotImplementedError
class HomeAssistant(Provider):
 def __init__(self,url=None,token=None):self.url=(url or os.getenv('HOME_ASSISTANT_URL','')).rstrip('/');self.token=token or os.getenv('HOME_ASSISTANT_TOKEN','')
 def ready(self):return bool(self.url and self.token)
 def _call(self,method,path,payload=None):
  if not self.ready():return IntegrationResult(False,error='Home Assistant configuration required')
  return request(method,self.url+'/api'+path,{'Authorization':'Bearer '+self.token},payload)
 def discover(self):return self._call('GET','/states')
 def state(self,device):return self._call('GET','/states/'+device)
 def command(self,device,action,value=None):
  if not policy.check('network.change',{'device':device,'action':action}).allowed:return IntegrationResult(False,error='authorization required',environment_ready=self.ready())
  domain=device.split('.')[0];return self._call('POST',f'/services/{domain}/{action}',{'entity_id':device,**({'value':value} if value is not None else {})})
class SmartHome:
 def __init__(self,provider=None):self.provider=provider or HomeAssistant()
 def discover(self):return self.provider.discover()
 def execute(self,device,action,value=None,verify=True):
  result=self.provider.command(device,action,value)
  if not result.ok or not verify:return result
  observed=self.provider.state(device);return IntegrationResult(observed.ok,{'command':result.data,'observed':observed.data},observed.error,observed.environment_ready)
smart_home=SmartHome()
