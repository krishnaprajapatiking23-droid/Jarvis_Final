from agents.manager import run_agent

while True:

    agent = input("Agent (business/coding): ").strip().lower()

    if agent == "exit":
        break

    command = input("Command: ")

    print("\n========================\n")

    result = run_agent(agent, command)

    print(result)

    print("\n========================\n")