"""Short-lived, thread-safe SQLite access (BUG 7).

The rule enforced here: a transaction never spans a network/LLM call. A
20-30 second generation must happen *between* transactions, so writers do
not hold locks while the model is thinking.

Provided:
* one connection per operation (never shared across threads)
* WAL journal + busy timeout
* bounded retry with exponential backoff on "database is locked"
* explicit rollback
* a ``no_transaction`` guard that raises :class:`TransactionMisuse` when a
  long call is attempted inside a transaction
"""

from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

__all__ = [
    "SQLiteDatabase",
    "TransactionMisuse",
    "database",
    "DEFAULT_BUSY_TIMEOUT",
    "MAX_RETRIES",
]

log = logging.getLogger(__name__)

DEFAULT_BUSY_TIMEOUT = 15.0
MAX_RETRIES = 6
BASE_BACKOFF = 0.02
MAX_BACKOFF = 0.5
SLOW_TRANSACTION_WARNING = 2.0
RETRYABLE = ("database is locked", "database table is locked", "database is busy")


class TransactionMisuse(RuntimeError):
    """Raised when a long-running call is made inside a transaction."""


def _is_retryable(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in RETRYABLE)


class SQLiteDatabase:
    """Connection-per-operation SQLite wrapper."""

    def __init__(self, path: Any, busy_timeout: float = DEFAULT_BUSY_TIMEOUT):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout = float(busy_timeout)
        self._schema_lock = threading.RLock()
        self._local = threading.local()

    # ------------------------------------------------------------ connection
    def connect(self) -> sqlite3.Connection:
        """Open a fresh connection owned by the calling thread."""
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout,
            isolation_level=None,  # explicit BEGIN/COMMIT only
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=%d" % int(self.busy_timeout * 1000))
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @property
    def in_transaction(self) -> bool:
        """True while this thread holds an open transaction."""
        return bool(getattr(self._local, "depth", 0))

    # ----------------------------------------------------------------- retry
    def _with_retry(
        self,
        work: Callable[[sqlite3.Connection], Any],
        label: str = "operation",
    ) -> Any:
        last: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                with closing(self.connect()) as connection:
                    return work(connection)
            except sqlite3.OperationalError as error:
                if not _is_retryable(error):
                    raise
                last = error
                delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                delay += random.uniform(0, BASE_BACKOFF)
                log.debug(
                    "%s contended (attempt %d/%d): %s",
                    label,
                    attempt + 1,
                    MAX_RETRIES,
                    error,
                )
                time.sleep(delay)
        raise sqlite3.OperationalError(
            f"{label} failed after {MAX_RETRIES} attempts: {last}"
        )

    def _begin(self, connection: sqlite3.Connection, immediate: bool = True) -> None:
        """Start a transaction, retrying briefly if the lock is contended."""
        statement = "BEGIN IMMEDIATE" if immediate else "BEGIN"
        last: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                connection.execute(statement)
                return
            except sqlite3.OperationalError as error:
                if not _is_retryable(error):
                    raise
                last = error
                delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                time.sleep(delay + random.uniform(0, BASE_BACKOFF))
        raise sqlite3.OperationalError(f"could not begin transaction: {last}")

    # ------------------------------------------------------------ operations
    def execute(
        self,
        sql: str,
        params: Sequence[Any] = (),
        fetch: bool = False,
    ) -> Any:
        """Run one statement in its own short transaction."""

        def work(connection: sqlite3.Connection) -> Any:
            cursor = connection.execute(sql, tuple(params))
            if fetch:
                return [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return cursor.rowcount

        return self._with_retry(work, "execute")

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        """Read-only helper returning a list of dicts."""
        return self.execute(sql, params, fetch=True)

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> int:
        """Insert/update many rows in one short transaction."""

        def work(connection: sqlite3.Connection) -> int:
            self._begin(connection)
            try:
                cursor = connection.executemany(sql, [tuple(row) for row in rows])
                connection.commit()
                return cursor.rowcount
            except Exception:
                connection.rollback()
                raise

        return self._with_retry(work, "execute_many")

    def script(self, sql: str) -> None:
        """Run a schema script (serialised across threads)."""
        with self._schema_lock:
            self._with_retry(lambda connection: connection.executescript(sql), "script")

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """Short write transaction. Never wrap an LLM/network call in this."""
        connection = self.connect()
        self._local.depth = getattr(self._local, "depth", 0) + 1
        started = time.monotonic()
        try:
            self._begin(connection, immediate)
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception as rollback_error:
                log.warning("rollback failed: %r", rollback_error)
            raise
        finally:
            self._local.depth = max(0, getattr(self._local, "depth", 1) - 1)
            connection.close()
            elapsed = time.monotonic() - started
            if elapsed > SLOW_TRANSACTION_WARNING:
                log.warning(
                    "transaction held for %.1fs - move slow work outside it", elapsed
                )

    @contextmanager
    def no_transaction(self, label: str = "long operation") -> Iterator[None]:
        """Guard for slow work (LLM calls) that must hold no database lock."""
        if self.in_transaction:
            raise TransactionMisuse(
                f"{label} must not run inside a database transaction"
            )
        yield

    # ---------------------------------------------------------------- health
    def table_names(self) -> List[str]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row["name"] for row in rows]

    def health(self) -> Dict[str, Any]:
        """Report journal mode, busy timeout and basic reachability."""

        def work(connection: sqlite3.Connection) -> Dict[str, Any]:
            journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
            timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            return {
                "path": str(self.path),
                "journal_mode": journal,
                "busy_timeout": float(timeout) / 1000.0,
                "ok": True,
            }

        try:
            return self._with_retry(work, "health")
        except Exception as error:
            return {"path": str(self.path), "ok": False, "error": repr(error)}


def database(path: Any = "data/jarvis.db") -> SQLiteDatabase:
    """Factory used across the project."""
    return SQLiteDatabase(path)
