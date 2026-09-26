"""Single-command probe to confirm brain.process() returns or hangs."""
import sys
import time

sys.path.insert(0, r"C:\Users\Yogi\.minimax-agent\projects\Jarvis_Pro_Batch3g\proj")

t0 = time.time()
print("[boot] importing brain...", flush=True)
from brains_v2.manager import brain
print(f"[boot] brain imported in {time.time()-t0:.1f}s", flush=True)

t0 = time.time()
print("[run] brain.process('hello') ...", flush=True)
try:
    r = brain.process("hello")
    print(f"[run] returned in {time.time()-t0:.1f}s -> {type(r).__name__}", flush=True)
    print(f"[run] reply={r.get('reply')!r}" if isinstance(r, dict) else f"[run] value={r!r}", flush=True)
except Exception as e:
    print(f"[run] EXC {type(e).__name__}: {e}", flush=True)

t0 = time.time()
print("[run] brain.process('add note buy milk') ...", flush=True)
try:
    r = brain.process("add note buy milk")
    print(f"[run] returned in {time.time()-t0:.1f}s -> {type(r).__name__}", flush=True)
    print(f"[run] reply={r.get('reply')!r}" if isinstance(r, dict) else f"[run] value={r!r}", flush=True)
except Exception as e:
    print(f"[run] EXC {type(e).__name__}: {e}", flush=True)

print("[done]", flush=True)
