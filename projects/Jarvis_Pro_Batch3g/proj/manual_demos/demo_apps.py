from automation.apps import open_app

while True:

    command = input("Command: ")

    if command.lower() == "exit":
        break

    result = open_app(command)

    print(result)