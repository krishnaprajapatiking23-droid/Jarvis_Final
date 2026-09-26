from tools.registry import registry
def register(name,function,**meta):return registry.register_tool(name,function,**meta)
def execute(name,*args,**kwargs):return registry.execute_tool(name,*args,**kwargs)
def available():registry.bootstrap();return registry.list_tools()
