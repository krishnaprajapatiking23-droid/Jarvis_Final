from .engine import engine
class JarvisAGIBridge:
 def __init__(self):self.last=None
 def analyze(self,command):self.last=engine.understand(command);return self.last
bridge=JarvisAGIBridge()
