from intelligence.manager import intelligence_manager
from intelligence.planner import create_plan

while True:

    command = input("You : ")

    if command.lower() == "exit":
        break

    request = intelligence_manager(command)

    plan = create_plan(request)

    print()

    print("Plan :")

    for step in plan:

        print("-", step)

    print()