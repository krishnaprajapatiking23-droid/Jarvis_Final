from business.manager import business_manager

while True:

    text = input("Business : ")

    if text.lower() == "exit":
        break

    answer = business_manager(text)

    print("\n", answer)