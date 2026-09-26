from brains_v2.server import *

print("=" * 60)
print("SPRINT A2 TEST")
print("=" * 60)

print(config.VERSION)

token = auth.create_token("Android")

print(auth.verify(token))

clients.add(token, "Android")

print(clients.count())

heartbeat.start()

print(encryption.hash("Jarvis"))

print("SPRINT A2 PASSED")