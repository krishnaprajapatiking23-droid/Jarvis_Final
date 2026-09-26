from ai.router import detect_agent

while True:

    text = input("You : ")

    if text == "exit":
        break

    print("Agent :", detect_agent(text))