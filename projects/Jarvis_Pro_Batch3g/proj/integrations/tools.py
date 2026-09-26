from .google_workspace import google_workspace
from .github import github
from .whatsapp import whatsapp
from .smart_home import smart_home
def google_tool(action,**kwargs):
 fn={'gmail.search':google_workspace.gmail_search,'gmail.get':google_workspace.gmail_get,'gmail.send':google_workspace.gmail_send,'calendar.list':google_workspace.calendar_events,'calendar.create':google_workspace.calendar_create,'calendar.update':google_workspace.calendar_update,'calendar.delete':google_workspace.calendar_delete,'drive.search':google_workspace.drive_search,'drive.get':google_workspace.drive_get}.get(action)
 if not fn:raise KeyError('unsupported Google action')
 return fn(**kwargs)
def github_tool(action,**kwargs):
 fn={'repos':github.repositories,'issues':github.issues,'pulls':github.pulls,'file':github.file,'issue.create':github.create_issue}.get(action)
 if not fn:raise KeyError('unsupported GitHub action')
 return fn(**kwargs)
def whatsapp_tool(action='send',**kwargs):
 if action!='send':raise KeyError('unsupported WhatsApp action')
 return whatsapp.send(**kwargs)
def smart_home_tool(action,**kwargs):
 if action=='discover':return smart_home.discover()
 if action=='execute':return smart_home.execute(**kwargs)
 raise KeyError('unsupported smart-home action')
