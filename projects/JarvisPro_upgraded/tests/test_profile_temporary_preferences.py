"""Section 8 - temporary vs permanent preferences.

A temporary preference must behave exactly like a permanent one until it
expires, disappear afterwards, survive a restart while still valid, and stay
visible in history() once it has lapsed.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.profile_store import ProfileStore, _expired, _utc, _utc_in


def _store():
    return ProfileStore(db_path=os.path.join(tempfile.mkdtemp(), "profile.db"))


# ---------------------------------------------------------------- helpers
def test_expired_helper_handles_none_and_order():
    assert _expired(None) is False
    assert _expired("") is False
    assert _expired(_utc_in(-10)) is True
    assert _expired(_utc_in(3600)) is False


def test_utc_in_is_chronologically_comparable():
    """Fixed-width UTC strings must compare correctly as plain strings."""
    assert _utc_in(-60) < _utc() <= _utc_in(60)


# ---------------------------------------------------------------- permanent
def test_permanent_preference_has_no_expiry():
    store = _store()
    attr = store.set("editor", "VS Code")
    assert attr.value == "VS Code"
    assert attr.expires_at is None
    assert attr.temporary is False


def test_permanent_preference_is_not_purged():
    store = _store()
    store.set("editor", "VS Code")
    assert store.purge_expired() == 0
    assert store.get("editor") == "VS Code"


# ---------------------------------------------------------------- temporary
def test_temporary_preference_readable_before_expiry():
    store = _store()
    attr = store.set("theme", "dark", ttl_seconds=3600)
    assert attr.temporary is True
    assert attr.expires_at
    assert store.get("theme") == "dark"


def test_temporary_preference_is_gone_after_expiry():
    store = _store()
    store.set_temporary("focus_mode", "on", ttl_seconds=1)
    assert store.get("focus_mode") == "on"
    time.sleep(1.2)
    assert store.get("focus_mode") is None
    assert store.attribute("focus_mode") is None


def test_expired_preference_falls_back_to_default():
    store = _store()
    store.set_temporary("verbosity", "terse", ttl_seconds=1)
    time.sleep(1.2)
    assert store.get("verbosity", "normal") == "normal"


def test_ttl_must_be_positive():
    store = _store()
    for bad in (0, -1):
        try:
            store.set("x", "y", ttl_seconds=bad)
        except ValueError:
            continue
        raise AssertionError("ttl_seconds=%r should be rejected" % bad)


# ---------------------------------------------------------------- snapshot
def test_snapshot_marks_temporary_and_hides_expired():
    store = _store()
    store.set("editor", "VS Code")
    store.set_temporary("theme", "dark", ttl_seconds=3600)
    store.set_temporary("gone", "x", ttl_seconds=1)
    time.sleep(1.2)

    snap = store.snapshot()
    assert snap["editor"]["temporary"] is False
    assert snap["theme"]["temporary"] is True
    assert "gone" not in snap


# ---------------------------------------------------------------- purge
def test_purge_removes_only_expired_and_keeps_history():
    store = _store()
    store.set("editor", "VS Code")
    store.set_temporary("theme", "dark", ttl_seconds=1)
    time.sleep(1.2)

    assert store.purge_expired() == 1
    assert store.get("editor") == "VS Code"
    assert store.get("theme") is None

    reasons = [row["reason"] for row in store.history("theme")]
    assert "expired" in reasons, reasons


# ---------------------------------------------------------------- lifecycle
def test_make_permanent_clears_the_expiry():
    store = _store()
    store.set_temporary("theme", "dark", ttl_seconds=1)
    promoted = store.make_permanent("theme")
    assert promoted is not None
    assert promoted.expires_at is None
    time.sleep(1.2)
    assert store.get("theme") == "dark"


def test_make_permanent_on_missing_key_returns_none():
    assert _store().make_permanent("nothing") is None


def test_temporary_can_overwrite_permanent_and_back():
    store = _store()
    store.set("theme", "light")
    store.set_temporary("theme", "dark", ttl_seconds=1)
    assert store.get("theme") == "dark"
    time.sleep(1.2)
    # The temporary value lapsed; it does not silently resurrect the old one.
    assert store.get("theme") is None
    store.set("theme", "light")
    assert store.get("theme") == "light"


# ---------------------------------------------------------------- persistence
def test_temporary_preference_survives_a_restart():
    path = os.path.join(tempfile.mkdtemp(), "profile.db")
    first = ProfileStore(db_path=path)
    first.set_temporary("theme", "dark", ttl_seconds=3600)

    reopened = ProfileStore(db_path=path)
    assert reopened.get("theme") == "dark"
    assert reopened.attribute("theme").temporary is True


def test_expiry_is_enforced_after_a_restart():
    path = os.path.join(tempfile.mkdtemp(), "profile.db")
    first = ProfileStore(db_path=path)
    first.set_temporary("theme", "dark", ttl_seconds=1)
    time.sleep(1.2)

    reopened = ProfileStore(db_path=path)
    assert reopened.get("theme") is None


def test_migration_adds_column_to_an_old_database():
    """A profile.db written before this feature must still open."""
    import sqlite3

    path = os.path.join(tempfile.mkdtemp(), "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE attributes (subject TEXT, key TEXT, value TEXT,"
        " confidence REAL, source TEXT, version INTEGER, updated_at TEXT,"
        " evidence_count INTEGER DEFAULT 0, PRIMARY KEY (subject, key))"
    )
    conn.execute(
        "INSERT INTO attributes VALUES('owner','editor','\"vim\"',0.9,"
        "'user_statement',1,'2020-01-01T00:00:00',0)"
    )
    conn.commit()
    conn.close()

    store = ProfileStore(db_path=path)
    # Pre-existing attributes stay readable and are permanent.
    assert store.get("editor") == "vim"
    assert store.attribute("editor").expires_at is None
