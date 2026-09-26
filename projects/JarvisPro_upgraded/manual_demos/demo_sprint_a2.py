# BUG FIX (two bugs):
# 1. This did ``from brains_v2.server import *`` and then read ``config``,
#    which was never imported/exported by brains_v2/server/__init__.py, so
#    the name did not exist -- NameError: name 'config' is not defined.
#    Fixed at the source (__init__.py now exports it); nothing to do here.
# 2. ``auth`` is constructed with ``require_pairing=True``, a deliberate
#    security default -- it must refuse to mint tokens until a pairing
#    secret is configured, which is correct behaviour, not a bug. This demo
#    sets one so it can actually demonstrate the pairing flow instead of
#    tripping the guard it exists to enforce.
import os

os.environ.setdefault("JARVIS_PAIRING_SECRET", "demo-pairing-secret")

from brains_v2.server import *

print("=" * 60)
print("SPRINT A2 TEST")
print("=" * 60)

print(config.VERSION)

token = auth.create_token("Android", pairing_secret=os.environ["JARVIS_PAIRING_SECRET"])

print(auth.verify(token))

clients.add(token, "Android")

print(clients.count())

heartbeat.start()

print(encryption.hash("Jarvis"))

print("SPRINT A2 PASSED")