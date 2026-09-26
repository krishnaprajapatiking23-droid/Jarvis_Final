import os,subprocess,sys
from pathlib import Path
from security.policy_engine import policy
class Desktop:
 def __init__(self):self.desktop=Path.home()/('OneDrive/Desktop' if (Path.home()/'OneDrive/Desktop').exists() else 'Desktop')
 def _open(self,target,label):
  d=policy.check('app.open',{'target':str(target)})
  if not d.allowed:return {'success':False,'message':d.reason}
  try:
   if sys.platform=='win32':os.startfile(str(target))
   elif sys.platform=='darwin':subprocess.Popen(['open',str(target)])
   else:subprocess.Popen(['xdg-open',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   return {'success':True,'message':label+' opened.'}
  except Exception as e:return {'success':False,'message':f'{type(e).__name__}: {e}'}
 def open_desktop(self):return self._open(self.desktop,'Desktop')
 def open_documents(self):return self._open(Path.home()/'Documents','Documents')
 def open_downloads(self):return self._open(Path.home()/'Downloads','Downloads')
 def open_pictures(self):return self._open(Path.home()/'Pictures','Pictures')
 def open_music(self):return self._open(Path.home()/'Music','Music')
 def open_videos(self):return self._open(Path.home()/'Videos','Videos')
 def show_desktop(self):
  from automation.windows import show_desktop
  return show_desktop()
 def open_this_pc(self):return self._open('shell:MyComputerFolder','This PC')
 def open_control_panel(self):return self._open('control','Control Panel')
 def open_settings(self):return self._open('ms-settings:','Windows Settings')
 def open_task_manager(self):return self._open('taskmgr','Task Manager')
 def open_recycle_bin(self):return self._open('shell:RecycleBinFolder','Recycle Bin')
desktop=Desktop()
