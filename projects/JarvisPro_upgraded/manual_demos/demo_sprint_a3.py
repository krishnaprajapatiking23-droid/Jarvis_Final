from brains_v2.memory import memory_intent

print("=" * 60)
print("SPRINT A3 TEST")
print("=" * 60)

memory_intent.remember(

    "business",

    "company",

    "Luxora Hub"

)

print(

    memory_intent.recall(

        "company"

    )

)

memory_intent.remember(

    "owner",

    "name",

    "Krishna"

)

print(

    memory_intent.recall(

        "name"

    )

)

print()

print("SPRINT A3 PASSED")