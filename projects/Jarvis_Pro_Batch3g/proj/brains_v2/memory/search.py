from .database import database
def search(text):
 cursor=database.execute('SELECT key,value FROM memories WHERE key LIKE ? OR value LIKE ?',(f'%{text}%',f'%{text}%'))
 return list(cursor.fetchall()) if hasattr(cursor,'fetchall') else list(cursor or [])
