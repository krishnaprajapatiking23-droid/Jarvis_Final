"""Probe specific commands one-at-a-time with extended timeout."""
import json, sys, time
sys.path.insert(0, r"C:\Users\Yogi\.minimax-agent\projects\Jarvis_Pro_Batch3g\proj")

from brains_v2.manager import brain

cmd = sys.argv[1]
t0 = time.time()
try:
    out = brain.process(cmd)
except BaseException as e:
    print(json.dumps({"cmd": cmd, "ok": False, "exc": f"{type(e).__name__}: {e}", "t": time.time()-t0}))
    sys.exit(2)
t = time.time()-t0
if isinstance(out, dict):
    print(json.dumps({
        "cmd": cmd, "ok": True, "t": round(t, 2),
        "type": out.get("type"),
        "reply": str(out.get("reply", ""))[:100],
        "verif_success": (out.get("verification") or {}).get("success") if isinstance(out.get("verification"), dict) else None,
        "keys": sorted(out.keys()),
    }))
else:
    print(json.dumps({"cmd": cmd, "ok": True, "t": round(t, 2), "non_dict": type(out).__name__, "value": str(out)[:80]}))
