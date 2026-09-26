from emotion.satisfaction import *

while True:

    text = input("You : ")

    if text.lower() == "exit":
        break

    if is_unsatisfied(text):

        print("\nJarvis :")
        print("I'm sorry my previous answer wasn't helpful.")
        print("Let me understand your needs better.\n")

        for question in clarification_questions():

            print("-", question)

    else:

        print("User is satisfied.")