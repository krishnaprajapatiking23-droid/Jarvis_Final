from __future__ import annotations
import re,uuid
from datetime import datetime,timedelta
from core.atomic_json import AtomicJSONStore
STORE=AtomicJSONStore('data/reminders.json',[])
def load():return STORE.load()
def save(rows):return STORE.save(rows)
def parse_time(text):
    """Parse a due time out of free text.

    BUG FIX: this used to understand only "in N units" and a bare "HH:MM".
    "at 5pm", "tomorrow at 9", "tonight" and "next monday" all returned None,
    and the caller then claimed no time had been given. Parsing is now
    delegated to brains_v2.nl_time, which covers the phrasings people use.
    """
    from brains_v2.nl_time import parse_time as _parse

    return _parse(text)
def add(title,time):
 due=time if isinstance(time,datetime) else parse_time(str(time))
 if not due:return 'I could not understand the reminder time.'
 item={'id':uuid.uuid4().hex[:8],'title':title.strip(),'time':due.isoformat(),'done':False};STORE.update(lambda r:r+[item]);return 'Reminder saved.'
def show():
 r=load();return 'No reminders.' if not r else '\n'.join(f"{i}. {x['title']} - {x['time']} ({'done' if x.get('done') else 'pending'})" for i,x in enumerate(r,1))
def mutate(token,op,title=None,when=None):
 ok={'v':False}
 def f(rows):
  try:i=int(token)-1
  except ValueError:i=next((j for j,x in enumerate(rows) if x.get('id')==token),-1)
  if not 0<=i<len(rows):return rows
  if op in ('cancel','delete'):rows.pop(i)
  elif op=='complete':rows[i]['done']=True
  else:
   if title:rows[i]['title']=title
   due=parse_time(when or '')
   if due:rows[i]['time']=due.isoformat()
  ok['v']=True;return rows
 STORE.update(f);return ok['v']
def check(now=None):
 now=now or datetime.now();due=[]
 def f(rows):
  for x in rows:
   try:
    if not x.get('done') and datetime.fromisoformat(x['time'])<=now:x['done']=True;due.append(x['title'])
   except Exception:continue
  return rows
 STORE.update(f);return f'Reminder: {due[0]}' if due else None
