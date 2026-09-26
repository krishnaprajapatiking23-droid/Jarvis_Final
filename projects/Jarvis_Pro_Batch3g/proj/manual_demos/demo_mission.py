from missions.manager import mission_manager

while True:

    goal = input("Mission : ")

    if goal.lower() == "exit":
        break

    answer = mission_manager(goal)

    print(answer)