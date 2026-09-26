"""
==========================================
JARVIS PRO
Memory Database
==========================================
"""

import sqlite3

DATABASE = "data/jarvis.db"


def connect():

    return sqlite3.connect(DATABASE)


def create_tables():

    conn = connect()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()