from engine.manager import jarvis_engine

username = "Krishna"

while True:

    command = input("You : ")

    if command.lower() == "exit":
        break

    print()

    print(jarvis_engine(command, username))

    print()