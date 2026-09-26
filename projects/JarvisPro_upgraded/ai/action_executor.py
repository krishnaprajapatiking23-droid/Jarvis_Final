from tools.registry import registry
def execute(action):
 text=str(action or '').strip().upper();mapping={'OPEN_NOTEPAD':'notepad','OPEN_CALCULATOR':'calculator','OPEN_PAINT':'paint','OPEN_CMD':'cmd','OPEN_EXPLORER':'explorer'}
 for key,target in mapping.items():
  if key in text:
   registry.bootstrap();return registry.execute_tool('open_app',f'open {target}')
 return {'success':False,'error':'unsupported action'}
