from datetime import datetime
from memory.visitor_database import connect

from security.owner_manager import is_owner


def register_visitor(name):

    name = name.strip().title()

    # Don't register the owner as a visitor
    if is_owner(name):
        return False

    conn = connect()
    cursor = conn.cursor()

    now = datetime.now()

    date = now.strftime("%d-%m-%Y")
    time = now.strftime("%I:%M %p")

    cursor.execute(
        "SELECT visit_count FROM visitors WHERE name=?",
        (name,)
    )

    row = cursor.fetchone()

    if row:

        count = row[0] + 1

        cursor.execute(
            """
            UPDATE visitors
            SET last_visit=?,
                visit_count=?
            WHERE name=?
            """,
            (f"{date} {time}", count, name)
        )

        conn.commit()
        conn.close()

        return False

    cursor.execute(
        """
        INSERT INTO visitors(
            name,
            first_visit,
            last_visit,
            visit_count
        )
        VALUES(?,?,?,?)
        """,
        (
            name,
            f"{date} {time}",
            f"{date} {time}",
            1
        )
    )

    conn.commit()
    conn.close()

    return True


def get_visitor_count(name):

    name = name.strip().title()

    if is_owner(name):
        return 0

    conn = connect()

    cursor = conn.cursor()

    cursor.execute(
        "SELECT visit_count FROM visitors WHERE name=?",
        (name,)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return 0


def save_conversation(name, message):

    conn = connect()

    cursor = conn.cursor()

    now = datetime.now()

    date = now.strftime("%d-%m-%Y")
    time = now.strftime("%I:%M %p")

    cursor.execute(
        """
        INSERT INTO conversations(
            visitor_name,
            date,
            time,
            message
        )
        VALUES(?,?,?,?)
        """,
        (
            name.title(),
            date,
            time,
            message
        )
    )

    conn.commit()

    conn.close()