from projects.manager import project_manager

while True:

    command = input("Project : ")

    if command.lower() == "exit":
        break

    print(project_manager(command))