from emotion.conversation_manager import conversation_manager

while True:

    user = input("You : ")

    if user.lower() == "exit":
        break

    answer = conversation_manager(user, "Krishna")

    print("\nJarvis :")
    print(answer)
