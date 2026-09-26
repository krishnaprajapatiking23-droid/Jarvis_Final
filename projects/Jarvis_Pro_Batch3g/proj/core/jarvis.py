from datetime import datetime
from security.owner_manager import is_owner
from core.greetings import get_greeting
from core.router import route_command
from core.startup import startup

from session.session_manager import (
    start_session,
    end_session,
    add_question,
)

from session.session_report import print_report

from memory.visitor_engine import (
    register_visitor,
    get_visitor_count,
    save_conversation,
)


class Jarvis:

    def __init__(self):

        print("\n=========================================")
        print("          JARVIS PRO V12")
        print("=========================================\n")

        print("Jarvis :", get_greeting("there"))
        print("Jarvis : I'm Jarvis.")
        print()

        self.user = input("Who is speaking? : ").strip().title()

        # Start Session
        start_session(self.user)

        first_time = register_visitor(self.user)

        print()

        startup(self.user)

        print()

        if is_owner(self.user):

            print(f"Jarvis : {get_greeting(self.user)} 👑")
            print("Jarvis : Owner access granted. 🔓")

        else:

            if first_time:

                print(f"Jarvis : Nice to meet you, {self.user}.")
                print(f"Jarvis : {get_greeting(self.user)}")
                print("Jarvis : Visitor Mode enabled.")

            else:

                visits = get_visitor_count(self.user)

                print(f"Jarvis : {get_greeting(self.user)}")
                print("Jarvis : Welcome back!")
                print(f"Jarvis : This is your visit number {visits}.")

        print("\nJarvis : How can I help you today?")

    def process(self, command):

        return route_command(command, self.user)

    def run(self):

        while True:

            command = input(f"\n{self.user} : ")

            # ==========================
            # Exit
            # ==========================
            if command.lower() == "exit":

                report = end_session()

                print_report(report)

                hour = datetime.now().hour

                if hour < 12:
                    message = "Have a wonderful day"

                elif hour < 18:
                    message = "Have a great afternoon"

                else:
                    message = "Have a pleasant evening"

                print(f"\nJarvis : Goodbye, {self.user}! 👋")
                print(f"Jarvis : {message}.")
                print("Jarvis : See you again soon!")

                break

            # ==========================
            # Count Questions
            # ==========================
            add_question()

            # ==========================
            # Process Command
            # ==========================
            answer = self.process(command)

            # ==========================
            # Save Conversation
            # ==========================
            save_conversation(
                self.user,
                command
            )

            # ==========================
            # Print Answer
            # ==========================
            print("\nJarvis :", answer)