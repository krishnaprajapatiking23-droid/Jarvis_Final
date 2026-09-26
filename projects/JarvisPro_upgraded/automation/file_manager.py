from pathlib import Path
import shutil
from security.policy_engine import policy
def _safe(path,action):return policy.check(action,{'path':str(Path(path).resolve())})
def delete_file(path):
 p=Path(path);d=_safe(p,'file.delete')
 if not d.allowed:return {'success':False,'error':d.reason,'confirmation_required':d.needs_confirmation}
 if not p.is_file():return {'success':False,'error':'file not found'}
 p.unlink();return {'success':True}
def delete_folder(path):
 p=Path(path);d=_safe(p,'folder.delete')
 if not d.allowed:return {'success':False,'error':d.reason,'confirmation_required':d.needs_confirmation}
 if not p.is_dir():return {'success':False,'error':'folder not found'}
 shutil.rmtree(p);return {'success':True}
def create_folder(path):
 p=Path(path);d=_safe(p,'file.create')
 if not d.allowed:return {'success':False,'error':d.reason}
 p.mkdir(parents=True,exist_ok=True);return {'success':True,'path':str(p)}
