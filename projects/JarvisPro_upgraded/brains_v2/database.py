from pathlib import Path
from database.connection import SQLiteDatabase
class BrainDatabase:
 def __init__(self,path=None):
  self.store=SQLiteDatabase(path or Path(__file__).parent/'data'/'brain_v2.db');self.store.script("CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY AUTOINCREMENT,command TEXT,reply TEXT,time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
 def save(self,command,reply):return self.store.execute('INSERT INTO memory(command,reply) VALUES(?,?)',(command,reply))
 def last(self):
  rows=self.store.execute('SELECT command,reply FROM memory ORDER BY id DESC LIMIT 1',fetch=True);return (rows[0]['command'],rows[0]['reply']) if rows else None
database=BrainDatabase()
