"""Trace where the hang occurs in conversation.understand()."""
import sys, time, traceback, signal
sys.path.insert(0, r"C:\Users\Yogi\.minimax-agent\projects\Jarvis_Pro_Batch3g\proj")

# Patch common suspects to log when they enter/exit
import conversation.temporal_parser as tp
orig_parse = tp.temporal_parser.parse
def traced_parse(text):
    print(f"[trace] temporal_parser.parse({text!r})", flush=True)
    t0 = time.time()
    r = orig_parse(text)
    print(f"[trace] temporal_parser.parse done in {time.time()-t0:.2f}s", flush=True)
    return r
tp.temporal_parser.parse = traced_parse

# Patch followup too
import conversation.followup as fu
orig_next = fu.next_question
def traced_next(command, ctx=None):
    print(f"[trace] followup.next_question({command!r})", flush=True)
    t0 = time.time()
    r = orig_next(command, ctx)
    print(f"[trace] followup done in {time.time()-t0:.2f}s -> {r}", flush=True)
    return r
fu.next_question = traced_next

from conversation.conversation_engine import conversation_engine

print("[trace] calling conversation_engine.understand('and what about yesterday')", flush=True)
t0 = time.time()
try:
    u = conversation_engine.understand("and what about yesterday")
    print(f"[trace] returned in {time.time()-t0:.2f}s, handled={u.handled}", flush=True)
except Exception as e:
    print(f"[trace] raised after {time.time()-t0:.2f}s: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
