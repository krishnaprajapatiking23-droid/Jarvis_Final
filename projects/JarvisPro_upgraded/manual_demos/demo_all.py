from core.router import route_command

username = "Krishna"

print("=" * 60)
print("          JARVIS PRO SYSTEM TEST")
print("=" * 60)

tests = [

    "Hello Jarvis",

    "Open Notepad",

    "Create folder TestFolder",

    "Create Meta Ads for mosquito door net",

    "Debug this Python error: ModuleNotFoundError",

    "Help me build a Shopify business"

]

for i, command in enumerate(tests, 1):

    print(f"\n\n========== TEST {i} ==========")
    print("User :", command)

    try:

        answer = route_command(command, username)

        print("\nJarvis :")
        print(answer)

    except Exception as e:

        print("\nERROR :")
        print(e)

print("\n")
print("=" * 60)
print("ALL TESTS COMPLETED")
print("=" * 60)