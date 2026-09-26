"""
Memory Manager
"""

from .database import database


class MemoryManager:

    def remember(

        self,

        category,

        key,

        value

    ):

        database.execute(

            """

            INSERT OR REPLACE INTO memories(

                category,

                key,

                value

            )

            VALUES(?,?,?)

            """,

            (

                category,

                key,

                value

            )

        )

        return True

    def recall(

        self,

        key

    ):

        row = database.execute(

            """

            SELECT value

            FROM memories

            WHERE key=?

            """,

            (

                key,

            )

        ).fetchone()

        if row:

            # BUG FIX: MemoryDatabase.execute() (via SQLiteDatabase, which
            # this class sits on top of) returns rows as dicts
            # (``[dict(row) for row in cursor.fetchall()]``), not tuples.
            # ``row[0]`` looked up the dict key 0, which never exists, and
            # raised KeyError: 0 on every recall -- reproducible via
            # manual_demos/demo_ai.py and demo_brain.py.
            return row["value"]

        return None

    def forget(

        self,

        key

    ):

        database.execute(

            """

            DELETE FROM memories

            WHERE key=?

            """,

            (

                key,

            )

        )

        return True


memory_intent = MemoryManager()