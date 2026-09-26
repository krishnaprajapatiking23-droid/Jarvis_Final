import shutil,time
try:
    import psutil
except ImportError:
    psutil = None
from .optimizer import optimizer

class PerformanceMonitor:
    def __init__(self):
        self.start_time=time.time();self.command_start=None;self.total_commands=0;self.total_replies=0;self.memory_updates=0;self.database_updates=0;self.last_command='';self.last_command_time=0
    def command_started(self,command):self.total_commands+=1;self.last_command=command;self.command_start=time.perf_counter()
    def start_timer(self):self.command_start=time.perf_counter()
    def command_finished(self,*args,**kwargs):
        if self.command_start is None:return 0
        elapsed=time.perf_counter()-self.command_start;self.last_command_time=round(elapsed,4);self.command_start=None
        try:optimizer.record('command',elapsed,True)
        except Exception:pass
        return elapsed
    finish=command_finished
    def update(self):return self.report()
    def reply_generated(self):self.total_replies+=1
    def memory_update(self):self.memory_updates+=1
    def database_saved(self):self.database_updates+=1
    def cpu_usage(self):return round(psutil.cpu_percent(interval=0) if psutil else 0.0,2)
    def memory_usage(self):
        if not psutil:return {'available':False,'reason':'psutil not installed'}
        m=psutil.virtual_memory();return {'used_percent':round(m.percent,2),'available_gb':round(m.available/1024**3,2),'total_gb':round(m.total/1024**3,2)}
    def disk_usage(self,path='/'):
        if psutil:d=psutil.disk_usage(path);return {'used_percent':round(d.percent,2),'free_gb':round(d.free/1024**3,2),'total_gb':round(d.total/1024**3,2)}
        d=shutil.disk_usage(path);return {'used_percent':round((d.used/d.total)*100,2),'free_gb':round(d.free/1024**3,2),'total_gb':round(d.total/1024**3,2)}
    def uptime(self):return round(time.time()-self.start_time,2)
    def report(self):return {'uptime':self.uptime(),'total_commands':self.total_commands,'total_replies':self.total_replies,'memory_updates':self.memory_updates,'database_updates':self.database_updates,'last_command':self.last_command,'last_command_time':self.last_command_time,'cpu_percent':self.cpu_usage(),'memory':self.memory_usage()}
    def system_report(self):return {'performance':self.report(),'optimizer':optimizer.report()}
performance=PerformanceMonitor()
