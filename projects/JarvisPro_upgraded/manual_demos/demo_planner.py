from business.planner import create_business_plan

while True:

    text = input("Goal : ")

    if text.lower() == "exit":
        break

    plan = create_business_plan(text)

    print("\n===== BUSINESS PLAN =====")

    for i, step in enumerate(plan, 1):

        print(f"{i}. {step}")

    print()