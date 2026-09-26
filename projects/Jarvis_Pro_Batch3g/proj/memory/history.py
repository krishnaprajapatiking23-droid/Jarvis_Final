from memory.visitor_database import connect


def visitor_history(name):

    conn = connect()

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
        date,
        time,
        message

        FROM conversations

        WHERE visitor_name=?

        ORDER BY id DESC
        """,
        (name.title(),)
    )

    rows = cursor.fetchall()

    conn.close()

    return rows