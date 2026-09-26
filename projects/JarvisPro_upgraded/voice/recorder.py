from pathlib import Path
SAMPLE_RATE=48000;DURATION=5
def record(duration=DURATION,device=None,path='voice/input.wav'):
 try:import sounddevice as sd;import soundfile as sf
 except ImportError as e:raise RuntimeError('microphone backend unavailable: '+str(e))
 try:
  audio=sd.rec(int(duration*SAMPLE_RATE),samplerate=SAMPLE_RATE,channels=1,dtype='int16',device=device);sd.wait();Path(path).parent.mkdir(parents=True,exist_ok=True);sf.write(path,audio,SAMPLE_RATE);return path
 except Exception as e:raise RuntimeError(f'microphone failure: {type(e).__name__}: {e}') from e
