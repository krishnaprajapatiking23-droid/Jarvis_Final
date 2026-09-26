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

            return row[0]

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