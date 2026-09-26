def print_report(report):

    print()

    print("========================================")
    print("         SESSION SUMMARY")
    print("========================================")

    print()

    print(f"User             : {report['user']}")

    print(f"Duration         : {report['duration']}")

    print(f"Questions        : {report['questions']}")

    print(f"Apps Opened      : {report['apps']}")

    print(f"Folders Created  : {report['folders']}")

    print(f"Goals Added      : {report['goals']}")

    print()

    print("========================================")