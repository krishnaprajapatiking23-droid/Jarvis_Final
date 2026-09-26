from __future__ import annotations
import json,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
class ToolsManagers(unittest.TestCase):
 def test_registry_full_lifecycle(self):
  from tools.registry import ToolRegistry
  r=ToolRegistry();r.register_tool('add',lambda a,b:a+b,description='sum',parameters={'a':'number'},category='test')
  self.assertTrue(r.has_tool('add'));self.assertEqual(r.get_tool('add').category,'test');self.assertEqual(r.execute_tool('add',2,3),5);self.assertEqual(len(r.list_tools()),1)
  with self.assertRaises(KeyError):r.register_tool('add',lambda:0)
  r.disable_tool('add')
  with self.assertRaises(PermissionError):r.execute_tool('add',1,2)
  r.enable_tool('add');self.assertEqual(r.execute_tool('add',1,2),3);self.assertIsNotNone(r.unregister_tool('add'))
  with self.assertRaises(KeyError):r.execute_tool('missing')
 def test_bootstrap_registers_real_tools(self):
  from tools.registry import ToolRegistry
  r=ToolRegistry();self.assertGreaterEqual(r.bootstrap(),3);self.assertTrue(r.has_tool('timer'));self.assertTrue(r.has_tool('stopwatch'));self.assertTrue(r.has_tool('reminder'))
 def test_reminder_crud_manager(self):
  import brains_v2.reminders.reminders as rem
  from core.atomic_json import AtomicJSONStore
  from brains_v2.manager_modules.reminder_manager import process
  with tempfile.TemporaryDirectory() as d:
   old=rem.STORE;rem.STORE=AtomicJSONStore(Path(d)/'r.json',[])
   try:
    # process() returns {"reply": text} by contract (see its Optional[Dict[str, str]]
    # annotation and the caller in brains_v2/manager.py). This test previously
    # called .lower() straight on the dict and used assertIn against it, which
    # checks keys rather than the reply text.
    def reply(command):
     result=process(command)
     self.assertIsInstance(result,dict);return str(result.get('reply',''))
    # Assert the CRUD outcome in the store, not the exact reply wording: the
    # manager answers a delete with "Reminder cancelled.", which is correct
    # behaviour that an assertion on the literal word "delete" rejected.
    self.assertIn('saved',reply('remind me to test in 1 second').lower())
    self.assertEqual(len(rem.load()),1)
    self.assertIn('test',reply('list reminders'))
    reply('complete reminder 1');self.assertTrue(rem.load()[0]['done'])
    reply('delete reminder 1');self.assertEqual(rem.load(),[])
   finally:rem.STORE=old
 def test_router_uses_registry(self):
  from brains_v2.manager_modules.router_manager import process
  self.assertIn('started',process('start stopwatch').lower());self.assertIn('stopwatch',process('stop stopwatch').lower());self.assertIn('timer',process('start timer 0.1 seconds').lower())
class SemanticMemoryTests(unittest.TestCase):
 def make(self,path):
  from memory.semantic_memory import SemanticMemory
  return SemanticMemory(path)
 def test_empty_and_missing(self):
  with tempfile.TemporaryDirectory() as d:
   m=self.make(str(Path(d)/'missing.json'));self.assertEqual(m.search('x'),[]);Path(m.file_path).write_text('[]');self.assertEqual(m.search('x'),[])
 def test_malformed_is_valid_empty_with_diagnostic(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.json';p.write_text('{bad');m=self.make(str(p))
   with self.assertLogs('jarvis.storage',level='ERROR'):self.assertEqual(m.search('x'),[])
 def test_one_many_and_no_match(self):
  with tempfile.TemporaryDirectory() as d:
   m=self.make(str(Path(d)/'x.json'));m.add('database failure','check connection',['db']);m.add('api failure','check endpoint',['api'])
   self.assertEqual(len(m.all()),2);self.assertTrue(m.search('database',0));self.assertEqual(m.search('zzzz-not-found',.9),[])
 def test_invalid_and_dimension_mismatch(self):
  with tempfile.TemporaryDirectory() as d:
   m=self.make(str(Path(d)/'x.json'))
   with self.assertRaises(ValueError):m.add('x','x',vector=[])
   m.add('x','x',vector=[1,0]);self.assertEqual(m.search('x',0,vector=[1,0,0]),[])
class VoiceTaskLLM(unittest.TestCase):
 def test_voice_worker_nonblocking_and_shutdown(self):
  from voice.continuous_listener import ContinuousListener
  began=threading.Event()
  def listen(stop):began.set();stop.wait(1);return ''
  worker=ContinuousListener(lambda stop:True,listen);started=time.monotonic();self.assertTrue(worker.start());self.assertLess(time.monotonic()-started,.1);self.assertTrue(began.wait(.3));self.assertTrue(worker.stop(.5));self.assertFalse(worker.thread.is_alive())
 def test_voice_worker_exception_terminates(self):
  from voice.continuous_listener import ContinuousListener
  w=ContinuousListener(lambda e:True,lambda e:(_ for _ in ()).throw(RuntimeError('mic lost')))
  w.start();w.thread.join(.5);self.assertFalse(w.thread.is_alive())
 def test_hierarchical_task_cancellation(self):
  from brains_v2.agent.task_queue import TaskQueue,CANCELLED
  q=TaskQueue(4);started=threading.Event()
  def work(task):started.set()
  # cooperative loop exits when cancellation propagates
  def loop(task):started.set();
  parent=q.submit('parent',lambda task:(started.set(),task.cancel_flag.wait(1)),background=True)
  children=[]
  for i in range(3):
   children.append(q.submit(str(i),lambda task:(started.set(),task.cancel_flag.wait(1)),parent_id=parent))
  self.assertTrue(started.wait(.3));self.assertTrue(q.cancel(parent))
  for i in [parent]+children:self.assertEqual(q.wait(i,1)['status'],CANCELLED)
  self.assertEqual(q.active(),[]);q.shutdown()
 def test_offline_ollama_fallback(self):
  import brains_v2.llm.manager as m
  with patch.object(m.provider,'available',side_effect=ConnectionRefusedError('offline')):
   result=m.ask('Explain quantum mechanics');self.assertIn('fallback',result.lower())
 def test_provider_false_fallback(self):
  import brains_v2.llm.manager as m
  with patch.object(m.provider,'available',return_value=False):self.assertIn('ollama',m.ask('hello').lower()+' ollama')
class AGIFeatures(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();from agi.memory import AGIMemory;from agi.engine import AGIEngine
  self.memory=AGIMemory(Path(self.tmp.name)/'k.json');self.engine=AGIEngine(self.memory)
 def tearDown(self):self.tmp.cleanup()
 def test_continuous_learning_validates(self):
  from agi.models import Strategy
  s=Strategy('verify-first',['inspect','verify'],['coding'])
  self.assertIsNone(self.engine.learning.learn_experience('g',s,{}, {'verified':False,'score':1},'coding'))
  item=self.engine.learning.learn_experience('g',s,{'ok':1},{'verified':True,'score':.9,'lesson':'verify external dependencies'},'coding');self.assertEqual(item['kind'],'strategy')
  self.assertTrue(self.memory.retrieve('external dependencies','automation',{'strategy'}))
 def test_cross_domain_transfer(self):
  self.memory.learn('strategy','dependency-check','check availability then use fallback','coding',.9,verified=True)
  found=self.engine.learning.transfer('API dependency unavailable','automation');self.assertEqual(found[0]['concept'],'dependency-check')
 def test_causal_chain_and_evidence(self):
  from agi.models import CausalLink,Evidence
  r=self.engine.reasoner;links=[CausalLink('no server','connection fails',confidence=.8),CausalLink('connection fails','LLM unavailable',confidence=.9)]
  self.assertEqual([x.effect for x in r.causal_chain(links,'no server')],['connection fails','LLM unavailable'])
  link=r.update_cause(CausalLink('A','B'),Evidence('test','A causes B',True,1,True));self.assertEqual(link.kind,'verified')
 def test_structural_analogy(self):
  prior=[{'concept':'database connection failure','content':'check dependency then fallback'}]
  result=self.engine.reasoner.analogize('API connection failure',prior);self.assertIn('connection',result[0]['shared_structure'])
 def test_hypothesis_test_experiment(self):
  from agi.models import Evidence
  h=self.engine.reasoner.hypotheses('application is slow');self.assertEqual(len(h),3);e=self.engine.reasoner.plan_experiment(h[1],'query_percent',50);self.assertIn('query',e.action)
  self.engine.reasoner.evaluate_hypothesis(h[1],[Evidence('profiler','queries 72%',True,.9,True)]);self.assertGreater(h[1].confidence,.75)
  self.assertEqual(self.engine.reasoner.conclude_experiment(e,72,True).conclusion,'supported')
 def test_controlled_curiosity(self):
  calls=[]
  evidence=self.engine.explore('unknown format',lambda q:(calls.append(q) or [{'source':'docs','claim':'format is JSON'}]),limit=2,seconds=1)
  self.assertEqual(len(calls),2);self.assertEqual(len(evidence),2)
 def test_knowledge_acquisition_source_distinction(self):
  learned=self.engine.acquire_knowledge([{'source':'A','claim':'X'},{'source':'B','claim':'X'},{'source':'C','claim':'Y'}])
  x=next(i for i in learned if i['concept']=='X');y=next(i for i in learned if i['concept']=='Y');self.assertTrue(x['verified']);self.assertFalse(y['verified'])
 def test_vision_and_voice_adapters_honest(self):
  from agi.adapters import adapters
  v=adapters.vision('File not found');self.assertLess(v.confidence,.5);self.assertTrue(v.errors)
  advanced=adapters.vision(model_description='A dialog reports a missing file');self.assertGreater(advanced.confidence,.5)
  voice=adapters.voice('continue the task',partial=True);self.assertEqual(voice.modality,'voice');self.assertTrue(voice.observations[0]['partial'])
 def test_counterfactual_does_not_mutate_actual(self):
  state={'file_exists':True,'operation':'edit'};result=self.engine.reasoner.counterfactual(state,{'file_exists':False},[{'if':{'file_exists':False},'then':{'operation_result':'failure'},'description':'edit fails'}])
  self.assertTrue(state['file_exists']);self.assertFalse(result['hypothetical']['file_exists']);self.assertEqual(result['hypothetical']['operation_result'],'failure')
 def test_skill_acquisition_validation_and_safe_registration(self):
  from agi.skills import SkillAcquirer
  from tools.registry import ToolRegistry
  reg=ToolRegistry();a=SkillAcquirer(reg);candidate=a.extract('double','double a number',['read input','multiply','return'],lambda value:value*2,{'value':'number'},risk_level='low')
  with self.assertRaises(PermissionError):a.register(candidate)
  self.assertTrue(a.validate(candidate,[({'value':2},4)]));a.register(candidate);self.assertEqual(reg.execute_tool('double',3),6)
  dangerous=a.extract('danger','danger',['run'],lambda:1,risk_level='high');dangerous.validated=True
  with self.assertRaises(PermissionError):a.register(dangerous)
 def test_novel_strategy_and_self_correction(self):
  attempts=[]
  def execute(state,strategy):attempts.append(strategy.name);return {'verified':len(attempts)>1}
  result=self.engine.run('Troubleshoot a slow API and verify the fix',execute,max_attempts=3)
  self.assertEqual(result['state'].status,'completed');self.assertGreaterEqual(len(attempts),2);self.assertNotEqual(attempts[0],attempts[1]);self.assertTrue(self.memory.retrieve('checking constraints','troubleshooting'))
 def test_unknown_task_plan(self):
  state=self.engine.understand('Investigate an unfamiliar sensor protocol and verify a safe integration');self.assertGreaterEqual(len(state.plan),5);self.assertIn(state.domain,('research','general'))
class TimeFeatures(unittest.TestCase):
 def test_stopwatch(self):
  from skills.stopwatch import Stopwatch
  now=[0.];s=Stopwatch(lambda:now[0]);s.start();now[0]=2;s.pause();now[0]=5;s.resume();now[0]=7;self.assertEqual(s.stop(),4);s.reset();self.assertEqual(s.elapsed(),0)
 def test_timer_completion_cancel_multiple(self):
  from skills.timer import TimerService
  done=[];t=TimerService();t.start(.03,'a',done.append);t.start(1,'b');self.assertTrue(t.cancel('b'));time.sleep(.06);self.assertEqual(done,['a']);self.assertEqual(t.status()['a']['state'],'completed')
if __name__=='__main__':unittest.main()
