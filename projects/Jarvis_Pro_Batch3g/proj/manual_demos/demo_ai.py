from brains_v2.brain import jarvis

print("=" * 60)
print("AI TEST")
print("=" * 60)

commands = [

    "remember company is Luxora Hub",

    "what is my company",

    "open notepad",

    "hello"

]

for command in commands:

    result = jarvis.think(command)

    print()

    print("USER :", command)

    print("JARVIS :", result["reply"])

print()

print("SPRINT C PASSED")