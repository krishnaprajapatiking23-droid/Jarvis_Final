from flask import jsonify,request
from .auth import auth
from .gateway import gateway
from .rate_limiter import limiter
def _bearer():
 h=request.headers.get('Authorization','');return h[7:] if h.startswith('Bearer ') else ''
def _limited():return not limiter.allow(request.remote_addr or 'unknown')
def register_routes(app):
 @app.get('/')
 def home():return jsonify({'project':'Jarvis','version':'final-hardened','status':'running'})
 @app.get('/api/ping')
 def ping():return jsonify({'status':'online'})
 @app.post('/api/login')
 def login():
  if _limited():return jsonify({'success':False,'error':'rate limit'}),429
  data=request.get_json(silent=True) or {}
  try:token=auth.create_token(data.get('device','Unknown'),tuple(data.get('scopes') or ['command:read']),data.get('pairing_secret'))
  except PermissionError as e:return jsonify({'success':False,'error':str(e)}),401
  return jsonify({'success':True,'token':token,'expires_in':auth.ttl})
 @app.post('/api/verify')
 def verify():
  if _limited():return jsonify({'valid':False,'error':'rate limit'}),429
  return jsonify({'valid':auth.verify(_bearer() or (request.get_json(silent=True) or {}).get('token',''))})
 @app.post('/api/command')
 def command():
  if _limited():return jsonify({'ok':False,'error':'rate limit'}),429
  token=_bearer();data=request.get_json(silent=True) or {};text=str(data.get('command','')).strip()
  if not token or not auth.verify(token):return jsonify({'ok':False,'error':'unauthorized'}),401
  if not text or len(text)>2000:return jsonify({'ok':False,'error':'invalid command'}),400
  record=auth.tokens.get(auth._hash(token),{});result=gateway.execute(text,set(record.get('scopes',())))
  return jsonify(result),200 if result.get('ok') else 403
