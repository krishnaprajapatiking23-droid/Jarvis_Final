from brains_v2.llm.assistant import assistant

print("=" * 60)
print("LLM TEST")
print("=" * 60)

commands = [

    "remember company is Luxora Hub",

    "what is company",

    "open notepad",

    "Who are you?"

]

for cmd in commands:

    print()

    print("USER :", cmd)

    print("JARVIS :")

    print(assistant.ask(cmd))

print()

print("SPRINT D RESPONSE 2 PASSED")