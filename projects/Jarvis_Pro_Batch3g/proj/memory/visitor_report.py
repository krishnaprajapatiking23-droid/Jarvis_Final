from memory.visitor_database import connect


def get_all_visitors():

    conn = connect()

    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        name,
        last_visit,
        visit_count
    FROM visitors
    ORDER BY last_visit DESC
    """)

    visitors = cursor.fetchall()

    conn.close()

    return visitors


def build_report():

    visitors = get_all_visitors()

    if not visitors:

        return "No visitors have used Jarvis yet."

    report = "\n===== VISITOR REPORT =====\n\n"

    for visitor in visitors:

        report += f"Name       : {visitor[0]}\n"
        report += f"Last Visit : {visitor[1]}\n"
        report += f"Visits     : {visitor[2]}\n"
        report += "--------------------------\n"

    return report