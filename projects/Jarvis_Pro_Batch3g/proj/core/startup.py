from memory.visitor_report import build_report


def startup(username):

    if username.lower() == "krishna":

        report = build_report()

        if report.strip():

            print("Jarvis : While you were away...\n")
            print(report)

    else:

        print(f"Jarvis : Welcome, {username}!")
        print("Jarvis : Visitor Mode enabled.")