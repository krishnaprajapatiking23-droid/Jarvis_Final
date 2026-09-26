from tools.registry import registry
def process(command):
 text=str(command or '').strip();low=text.lower();registry.bootstrap()
 for token,tool in [('remind','reminder'),('reminder','reminder'),('stopwatch','stopwatch'),('timer','timer')]:
  if token in low:return registry.execute_tool(tool,text)
 return None
