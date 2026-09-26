from coding.manager import coding_manager

while True:

    command = input("Coding : ")

    if command.lower() == "exit":
        break

    print()
    print(coding_manager(command))
    print()