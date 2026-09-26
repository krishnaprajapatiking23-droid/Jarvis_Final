import os,urllib.parse
from security.policy_engine import policy
from .http import request
from .base import IntegrationResult
class GitHub:
 def __init__(self,token=None,base='https://api.github.com'):self.token=token or os.getenv('GITHUB_TOKEN','');self.base=base.rstrip('/')
 def ready(self):return bool(self.token)
 def call(self,method,path,payload=None,write=False):
  if not self.token:return IntegrationResult(False,error='GitHub token required')
  if write and not policy.check('network.change',{'service':'github','path':path}).allowed:return IntegrationResult(False,error='authorization required',environment_ready=True)
  return request(method,self.base+path,{'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json'},payload)
 def repositories(self):return self.call('GET','/user/repos?per_page=50')
 def issues(self,repo):return self.call('GET',f'/repos/{repo}/issues')
 def pulls(self,repo):return self.call('GET',f'/repos/{repo}/pulls')
 def file(self,repo,path,ref='main'):return self.call('GET',f'/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}')
 def create_issue(self,repo,title,body=''):return self.call('POST',f'/repos/{repo}/issues',{'title':title,'body':body},True)
github=GitHub()
