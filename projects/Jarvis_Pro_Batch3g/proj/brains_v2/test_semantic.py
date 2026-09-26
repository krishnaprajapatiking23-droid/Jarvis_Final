from brains_v2.semantic import remember
from brains_v2.semantic import recall

remember("Krishna is building a private Jarvis AI.")

remember("Jarvis uses Qwen3 locally.")

remember("The project uses Brain V2.")

print()

print(recall("Jarvis"))

print()

print(recall("Brain"))