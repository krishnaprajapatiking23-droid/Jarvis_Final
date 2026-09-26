from brains_v2 import process

tests = [

    "Hello",

    "What is recursion?",

    "Explain quantum computing simply.",

    "Open Notepad"

]

for command in tests:

    data = process(command)

    print()

    print("=" * 60)

    print(command)

    print()

    print("LLM Used:", data["llm_used"])

    print()

    print(data["reply"])