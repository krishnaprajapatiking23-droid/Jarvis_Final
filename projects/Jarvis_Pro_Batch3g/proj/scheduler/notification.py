def notify(reminder):
    print("===================================")
    print("🔔 JARVIS REMINDER")
    print("-----------------------------------")

    task = reminder.get("task", "No Task")
    print(f"Task : {task}")

    print("===================================")