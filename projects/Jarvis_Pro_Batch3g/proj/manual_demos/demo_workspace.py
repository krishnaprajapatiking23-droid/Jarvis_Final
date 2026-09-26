from workspace.manager import workspace_manager

while True:

    command = input("Workspace : ")

    if command.lower() == "exit":
        break

    print()

    print(workspace_manager(command))

    print()