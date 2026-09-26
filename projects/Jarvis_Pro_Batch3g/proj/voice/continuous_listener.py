from __future__ import annotations
import logging,threading
log=logging.getLogger('jarvis.voice.listener')
class ContinuousListener:
 def __init__(self,wake=None,listen=None,route=None,speak=None,on_result=None):
  self.wake=wake;self.listen=listen;self.route=route;self.speak=speak;self.on_result=on_result;self.stop_event=threading.Event();self.thread=None
 def start(self):
  if self.thread and self.thread.is_alive():return False
  self.stop_event.clear();self.thread=threading.Thread(target=self._run,name='jarvis-voice-listener',daemon=True);self.thread.start();return True
 def _run(self):
  while not self.stop_event.is_set():
   try:
    if self.wake and not self.wake(self.stop_event):continue
    if self.stop_event.is_set():break
    command=self.listen(self.stop_event) if self.listen else ''
    if not command:continue
    if command.lower()=='exit':break
    answer=self.route(command) if self.route else ''
    if self.on_result:self.on_result(command,answer)
    if self.speak and answer:self.speak(answer)
   except Exception as e:log.exception('voice worker failed: %s',e);break
 def stop(self,timeout=2):
  self.stop_event.set()
  if self.thread:self.thread.join(timeout);return not self.thread.is_alive()
  return True
def _legacy():
 from voice.wake_word import wait_for_wake_word;from voice.voice_engine import listen_and_speak;from voice.speaker import speak;from core.router import route_command;from conversation.identity import identity
 return ContinuousListener(lambda e:(wait_for_wake_word() or True),lambda e:listen_and_speak(),lambda c:route_command(c,identity.owner()),speak)
_listener=None
def start():
 global _listener
 _listener=_legacy();_listener.start();return _listener
def stop():return _listener.stop() if _listener else True
