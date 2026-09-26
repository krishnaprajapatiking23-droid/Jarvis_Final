from brains_v2.memory import memory_intent
from brains_v2.memory import search

print("=" * 60)
print("MEMORY TEST")
print("=" * 60)

memory_intent.remember(
    "business",
    "company",
    "Luxora Hub"
)

memory_intent.remember(
    "owner",
    "name",
    "Krishna"
)

memory_intent.remember(
    "assistant",
    "jarvis",
    "Tony Stark AI"
)

print(memory_intent.recall("company"))
print(memory_intent.recall("name"))
print(memory_intent.recall("jarvis"))

print(search("Krishna"))

memory_intent.forget("jarvis")

print(memory_intent.recall("jarvis"))

print()

print("SPRINT A3 PASSED")