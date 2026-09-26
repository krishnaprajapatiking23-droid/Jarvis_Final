from __future__ import annotations
import os,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch

class ImportArchitecture(unittest.TestCase):
 def test_corrected_imports(self):
  import brains_v2.brain.context,brains_v2.planner.scheduler,brains_v2.self_learning.analyzer,brains_v2.vision.ocr,thinking.observer
 def test_brain_authoritative_import(self):
  from brains_v2.manager import BrainV2
  self.assertTrue(BrainV2())

class StorageConcurrency(unittest.TestCase):
 def test_sqlite_concurrent_transactions(self):
  from database.connection import SQLiteDatabase
  with tempfile.TemporaryDirectory() as d:
   db=SQLiteDatabase(Path(d)/'x.db');db.script('CREATE TABLE c(n INTEGER); INSERT INTO c VALUES(0);')
   def add():
    for _ in range(30):
     with db.transaction() as c:c.execute('UPDATE c SET n=n+1')
   ts=[threading.Thread(target=add) for _ in range(4)]
   [t.start() for t in ts];[t.join() for t in ts]
   self.assertEqual(db.execute('SELECT n FROM c',fetch=True)[0]['n'],120)
 def test_atomic_json_concurrent_writes(self):
  from core.atomic_json import AtomicJSONStore
  with tempfile.TemporaryDirectory() as d:
   s=AtomicJSONStore(Path(d)/'x.json',[])
   ts=[threading.Thread(target=lambda i=i:s.update(lambda rows:rows+[i])) for i in range(40)]
   [t.start() for t in ts];[t.join() for t in ts]
   self.assertEqual(sorted(s.load()),list(range(40)))

class Security(unittest.TestCase):
 def test_safe_math_blocks_code(self):
  from security.safe_math import evaluate
  self.assertEqual(evaluate('2+3*4'),14)
  with self.assertRaises(ValueError):evaluate('__import__("os").system("id")')
 def test_sandbox_safe_forbidden_timeout(self):
  from security.code_sandbox import run_python
  self.assertEqual(run_python('print(2+2)').stdout.strip(),'4')
  with self.assertRaises(PermissionError):run_python('import socket')
  self.assertTrue(run_python('while True: pass',timeout=.2).timed_out)
 def test_policy_path_and_critical(self):
  from security.policy_engine import policy
  self.assertFalse(policy.check('file.delete',{'path':'/etc/passwd'}).allowed)
  d=policy.check('system.shutdown');self.assertFalse(d.allowed);self.assertTrue(d.needs_confirmation)
 def test_power_does_not_execute_without_confirmation(self):
  from automation.power import power
  with patch('automation.power.subprocess.run') as run:
   result=power.shutdown();self.assertFalse(result['success']);run.assert_not_called()

class ToolsAndTime(unittest.TestCase):
 def test_registry_all_major_categories(self):
  from tools.registry import ToolRegistry
  r=ToolRegistry();self.assertGreaterEqual(r.bootstrap(),9);self.assertEqual(r.errors,[])
  self.assertTrue({'timer','stopwatch','reminder','open_app','open_website','google_workspace','github','whatsapp','smart_home'}<=set(x.name for x in r.list_tools()))
 def test_timer_pause_resume_completion(self):
  from skills.timer import TimerService
  done=[];t=TimerService();i=t.start(.08,'x',done.append);time.sleep(.02);self.assertTrue(t.pause(i));left=t.remaining(i);time.sleep(.08);self.assertEqual(t.status()[i]['state'],'paused');self.assertTrue(t.resume(i));time.sleep(left+.04);self.assertEqual(done,['x']);self.assertEqual(t.events[0]['type'],'timer.completed')

class CompanionServer(unittest.TestCase):
 def test_token_expiry_scopes_pairing(self):
  from brains_v2.server.auth import AuthManager
  now=[10.];a=AuthManager(ttl=5,clock=lambda:now[0])
  with patch.dict(os.environ,{'JARVIS_PAIRING_SECRET':'secret'}):
   with self.assertRaises(PermissionError):a.create_token('phone',pairing_secret='bad')
   token=a.create_token('phone',('command:read',),'secret')
  self.assertTrue(a.verify(token,'command:read'));self.assertFalse(a.verify(token,'command:execute'));now[0]=16;self.assertFalse(a.verify(token))
 def test_gateway_scope_and_policy(self):
  from brains_v2.server.gateway import CommandGateway
  g=CommandGateway(lambda x:'ok')
  self.assertFalse(g.execute('open notepad',{'command:read'})['ok']);self.assertTrue(g.execute('hello',{'command:read'})['ok']);self.assertFalse(g.execute('shutdown computer',{'command:admin'})['ok'])
 def test_websocket_auth_cleanup(self):
  from brains_v2.server.auth import AuthManager
  from brains_v2.server.websocket import WebSocketHub
  a=AuthManager();token=a.create_token('p',('command:read',));sent=[];h=WebSocketHub(a);h.connect(token,sent.append);self.assertEqual(h.broadcast({'x':1}),1);self.assertEqual(sent,[{'x':1}])

class ExternalIntegrations(unittest.TestCase):
 def test_missing_credentials_are_explicit(self):
  from integrations.google_workspace import GoogleWorkspace
  from integrations.github import GitHub
  from integrations.whatsapp import CloudAPI
  from integrations.smart_home import HomeAssistant
  self.assertIn('required',GoogleWorkspace(token='').gmail_search('x').error)
  self.assertIn('required',GitHub(token='').repositories().error)
  self.assertIn('required',CloudAPI(token='',phone_id='').send('1','x').error)
  self.assertIn('required',HomeAssistant(url='',token='').discover().error)
 def test_smart_home_verifies_observed_state(self):
  from integrations.smart_home import SmartHome,Provider
  from integrations.base import IntegrationResult
  class Fake(Provider):
   def discover(self):return IntegrationResult(True,[])
   def command(self,d,a,v=None):return IntegrationResult(True,{'accepted':True},environment_ready=True)
   def state(self,d):return IntegrationResult(True,{'entity_id':d,'state':'on'},environment_ready=True)
  s=SmartHome(Fake());result=s.execute('light.bedroom','turn_on');self.assertTrue(result.ok);self.assertEqual(result.data['observed']['state'],'on')

class VoiceVisionAGI(unittest.TestCase):
 def test_voice_state_prevents_self_listening(self):
  from voice.state_machine import VoiceStateMachine,VoiceState
  s=VoiceStateMachine();s.transition(VoiceState.SPEAKING);self.assertFalse(s.can_listen());s.transition(VoiceState.IDLE);self.assertTrue(s.can_listen());s.stop();self.assertFalse(s.can_listen())
 def test_ocr_invalid_image(self):
  from vision.ocr import read
  r=read('/definitely/missing.png');self.assertFalse(r.ok);self.assertIn('invalid',r.error)
 def test_agi_failure_changes_strategy(self):
  from agi.memory import AGIMemory
  from agi.engine import AGIEngine
  with tempfile.TemporaryDirectory() as d:
   e=AGIEngine(AGIMemory(Path(d)/'k.json'));seen=[]
   result=e.run('Troubleshoot slow database safely',lambda state,strategy:(seen.append(strategy.name) or {'verified':len(seen)>1}),max_attempts=3)
   self.assertEqual(result['state'].status,'completed');self.assertNotEqual(seen[0],seen[1])

class FinalIntegrationChecks(unittest.TestCase):
 def test_global_server_requires_pairing_configuration(self):
  from brains_v2.server.auth import AuthManager
  a=AuthManager(require_pairing=True)
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(PermissionError):a.create_token('phone')
 def test_rate_limiter_stops_burst(self):
  from brains_v2.server.rate_limiter import RateLimiter
  r=RateLimiter(limit=2,window=10,clock=lambda:1)
  self.assertTrue(r.allow('x'));self.assertTrue(r.allow('x'));self.assertFalse(r.allow('x'))
 def test_gui_and_voice_modules_import_without_hardware(self):
  import gui.main_window,voice.manager
  self.assertTrue(hasattr(gui.main_window,'JarvisGUI'))
 def test_google_request_uses_real_https_url(self):
  import importlib
  module=importlib.import_module('integrations.google_workspace')
  client=module.GoogleWorkspace('token')
  with patch.object(module,'request') as call:
   call.return_value=module.IntegrationResult(True,[])
   client.gmail_search('urgent')
   self.assertTrue(call.call_args.args[1].startswith('https://gmail.googleapis.com/'))
 def test_android_companion_source_is_complete(self):
  root=Path(__file__).resolve().parents[1]
  text=(root/'android/app/src/main/java/com/jarvis/companion/JarvisClient.kt').read_text()
  self.assertIn('fun login',text);self.assertIn('Authorization',text);self.assertIn('fun command',text)

if __name__=='__main__':unittest.main()
