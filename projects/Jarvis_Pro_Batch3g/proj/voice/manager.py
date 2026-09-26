from conversation.identity import identity
from voice.state_machine import voice_state,VoiceState
def listen(owner=None):
 owner=owner or identity.owner()
 try:
  voice_state.transition(VoiceState.LISTENING)
  from voice.recorder import record
  from voice.recognizer import recognize
  text=recognize(record())
  if not text:return '',"Sorry, I couldn't hear you."
  voice_state.transition(VoiceState.PROCESSING)
  from core.router import route_command
  answer=route_command(text,owner)
  voice_state.transition(VoiceState.SPEAKING)
  from voice.speaker import speak
  speak(answer)
  return text,answer
 except Exception as e:return '',f'Voice unavailable: {type(e).__name__}: {e}'
 finally:
  if voice_state.state!=VoiceState.STOPPED:voice_state.transition(VoiceState.IDLE)
