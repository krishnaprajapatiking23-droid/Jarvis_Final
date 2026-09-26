import platform
import os


def startup():

    print("=" * 60)

    print("Jarvis Starting...")

    print("Operating System :", platform.system())

    print("Machine :", platform.machine())

    print("Python :", platform.python_version())

    print("Working Directory :", os.getcwd())

    print("=" * 60)


def choose_mode():

    print("\n==============================")
    print("        JARVIS PRO")
    print("==============================")
    print("1. Voice Mode")
    print("2. Developer Mode")
    print("==============================")

    while True:

        choice = input("Choose Mode (1/2): ").strip()

        if choice == "1":
            return "voice"

        elif choice == "2":
            return "developer"

        print("Invalid choice. Please enter 1 or 2.")