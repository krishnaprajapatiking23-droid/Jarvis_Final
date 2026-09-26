import sqlite3


DATABASE = "data/visitors.db"


def connect():
    return sqlite3.connect(DATABASE)


def create_tables():

    conn = connect()

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visitors(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT UNIQUE,

        first_visit TEXT,

        last_visit TEXT,

        visit_count INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        visitor_name TEXT,

        date TEXT,

        time TEXT,

        message TEXT
    )
    """)

    conn.commit()

    conn.close()