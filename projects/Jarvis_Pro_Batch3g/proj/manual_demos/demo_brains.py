from brains.manager import brain_manager

username = "Krishna"

while True:

    command = input("You : ")

    if command.lower() == "exit":
        break

    answer = brain_manager(command, username)

    print("\nJarvis :", answer)
    print()