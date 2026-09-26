from brains_v2.voice_v2 import pipeline
from brains_v2.config import settings
from brains_v2.startup import startup

print()

startup()
print("=" * 70)

print(f"JARVIS V1 - {settings['owner']}")

print("=" * 70)

pipeline.run()