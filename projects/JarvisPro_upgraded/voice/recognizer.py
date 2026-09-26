_model=None
def recognize(audio_file,model_name='small'):
 global _model
 try:import whisper
 except ImportError as e:raise RuntimeError('speech recognition backend unavailable: '+str(e))
 try:
  if _model is None:_model=whisper.load_model(model_name)
  result=_model.transcribe(audio_file,language='en',fp16=False,temperature=0);return str(result.get('text','')).strip()
 except Exception as e:raise RuntimeError(f'speech recognition failure: {type(e).__name__}: {e}') from e
