from __future__ import annotations
def respond(command,error=''):
 text=str(command or '').strip();low=text.lower()
 if not text:return 'Please provide a request.'
 if any(x in low for x in ('hello','hi ','hey')):return 'Hello. The local language model is unavailable, but core Jarvis tools are still working.'
 if 'time' in low:
  from datetime import datetime;return datetime.now().strftime('The current time is %H:%M.')
 if any(x in low for x in ('timer','stopwatch','reminder')):return 'The local model is unavailable. I can still run that command through the built-in tool router.'
 return 'Ollama is unavailable. Using the built-in fallback system; model-dependent answering is temporarily limited.'
