from pathlib import Path
from database.connection import SQLiteDatabase
class QueryResult:
 def __init__(self,rows=(),rowcount=0):self.rows=list(rows);self.rowcount=rowcount
 def fetchall(self):return list(self.rows)
 def fetchone(self):return self.rows[0] if self.rows else None
class MemoryDatabase:
 def __init__(self,path=None):
  self.store=SQLiteDatabase(path or Path('data')/'memory_v2.db');self.store.script("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT,key TEXT UNIQUE,value TEXT,created TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
 def execute(self,query,values=()):
  fetch=query.lstrip().upper().startswith(('SELECT','PRAGMA','WITH'))
  if fetch:return QueryResult(self.store.execute(query,values,fetch=True))
  return QueryResult(rowcount=self.store.execute(query,values))
database=MemoryDatabase()
