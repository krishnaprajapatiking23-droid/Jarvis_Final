from security.policy_engine import policy
class CommandGateway:
 def __init__(self,router=None):self.router=router
 def classify(self,text):
  low=text.lower()
  if any(x in low for x in ('shutdown','restart','delete ','format ','run code','shell ')):return 'command:admin','code.execute'
  if any(x in low for x in ('open ','send ','create ','change ','turn ')):return 'command:execute','browser.automate'
  return 'command:read','read'
 def execute(self,text,scopes):
  scope,action=self.classify(text)
  if scope not in scopes:return {'ok':False,'error':'scope denied'}
  d=policy.check(action,{'source':'companion','command':text[:200]})
  if not d.allowed:return {'ok':False,'error':d.reason,'confirmation_required':d.needs_confirmation}
  if self.router:return {'ok':True,'result':self.router(text)}
  from core.router import route_command
  return {'ok':True,'result':route_command(text,'companion')}
gateway=CommandGateway()
