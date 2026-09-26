from business.planner import execute_business_plan

while True:

    command = input("Goal : ")

    if command.lower() == "exit":
        break

    output = execute_business_plan(command)

    print("\n========== RESULT ==========\n")

    for title, result in output.items():

        print(f"\n===== {title} =====\n")

        print(result)

        print("\n")
    