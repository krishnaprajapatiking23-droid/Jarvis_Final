from ai.manager import ask

while True:

    question = input("You : ").strip()

    # Exit
    if question.lower() == "exit":
        break

    # Ignore empty input
    if not question:
        print("Please type something.")
        continue

    messages = [
        {
            "role": "user",
            "content": question
        }
    ]

    answer = ask(question, messages)

    print("\nJarvis :", answer)