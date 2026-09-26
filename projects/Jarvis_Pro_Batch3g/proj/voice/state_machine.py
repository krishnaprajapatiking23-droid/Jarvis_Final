from enum import Enum
import threading
class VoiceState(str,Enum):IDLE='idle';LISTENING='listening';PROCESSING='processing';SPEAKING='speaking';STOPPED='stopped';ERROR='error'
class VoiceStateMachine:
 def __init__(self):self._state=VoiceState.IDLE;self._lock=threading.RLock();self._stop=threading.Event();self.last_error=''
 @property
 def state(self):
  with self._lock:return self._state
 def transition(self,state,error=''):
  with self._lock:self._state=VoiceState(state);self.last_error=error
 def can_listen(self):return not self._stop.is_set() and self.state not in (VoiceState.SPEAKING,VoiceState.STOPPED)
 def stop(self):self._stop.set();self.transition(VoiceState.STOPPED)
 def reset(self):self._stop.clear();self.transition(VoiceState.IDLE)
voice_state=VoiceStateMachine()
