def create_report(results):

    report = "\n========== MISSION REPORT ==========\n"

    for task, result in results.items():

        report += f"\n{task}\n"
        report += "-" * 40 + "\n"
        report += str(result) + "\n"

    report += "\n===================================="

    return report