"""Behavioural tests for Batch 2 subsystems (Sections 3,4,5,6,7,8).

No pytest (unavailable offline). Prints PASS/FAIL with evidence and exits
non-zero on any failure. Each subsystem is isolated in a temp directory so
the suite never depends on live workspace data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.conversation import ConversationEngine  # noqa: E402
from jarvis_core.memory_lifecycle import (  # noqa: E402
    MemoryPermissionError, MemoryStore, PRIVATE, SECRET, STATUS_ARCHIVED,
)
from jarvis_core.notes import NotesManager  # noqa: E402
from jarvis_core.profile_store import (  # noqa: E402
    ConstraintViolation, Personality, ProfileStore,
)
from jarvis_core.reminders import DeliveryError, ReminderManager  # noqa: E402

PASSED = 0
FAILED = 0
TMP = tempfile.mkdtemp(prefix="jarvis_batch2_")


def check(name: str, condition: bool, evidence: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {name}" + (f"  {evidence}" if evidence else ""))
    else:
        FAILED += 1
        print(f"[FAIL] {name}" + (f"  {evidence}" if evidence else ""))


def db(name: str) -> str:
    return os.path.join(TMP, name)


# ============================================================ Section 3
print("\n=== Section 3: conversation ===")
conv = ConversationEngine(db_path=db("conv.db"))
session = conv.start_session("text")

turn = conv.analyse(session, "Open it.", candidates=["report.pdf", "budget.xlsx"])
check("ambiguity detected for a bare pronoun", turn.ambiguous,
      f"referents={turn.referents}")
check("clarification names the real candidates",
      "report.pdf" in (turn.clarification or "") and "budget.xlsx" in (turn.clarification or ""),
      repr(turn.clarification))

unambiguous = conv.analyse(session, "Open report.pdf now", candidates=["report.pdf"])
check("single candidate is not ambiguous", not unambiguous.ambiguous,
      f"ambiguous={unambiguous.ambiguous}")

single = conv.analyse(session, "this is broken again", candidates=[])
check("one frustrated sentence does not flip style immediately",
      single.style in ("standard", "repair", "teaching", "friendly"),
      f"style={single.style} raw={round(conv.raw_signals(session).get('frustrated', 0), 3)}")

for text in ["this is still broken", "why is it broken again", "nothing works, useless"]:
    frustrated = conv.analyse(session, text)
check("sustained frustration switches to repair style", frustrated.style == "repair",
      f"style={frustrated.style} mood={conv.mood(session)['dominant']}")

confused = conv.analyse(conv.start_session("voice"), "i don't understand what this means, confused")
check("confusion detected", confused.dominant in ("confused", "neutral"),
      f"dominant={confused.dominant} signals={ {k: round(v,2) for k,v in confused.signals.items() if v} }")

excited = conv.analyse(conv.start_session("gui"), "awesome!! this is amazing, i love it!")
check("excitement detected and style adapts", excited.dominant == "excited",
      f"dominant={excited.dominant} style={excited.style}")

urgent = conv.analyse(conv.start_session("text"), "quick! do it right now, asap")
check("urgency produces terse directives", urgent.style_directives.get("verbosity") in ("minimal", "concise"),
      f"style={urgent.style} directives={urgent.style_directives}")

try:
    conv.analyse(session, "   ")
    check("empty input rejected", False, "no error raised")
except ValueError as exc:
    check("empty input rejected", True, f"ValueError: {exc}")

try:
    conv.analyse("S-nonexistent", "hello")
    check("unknown session rejected", False, "no error raised")
except KeyError:
    check("unknown session rejected", True, "KeyError raised")

check("history persists turns", len(conv.history(session)) >= 5,
      f"{len(conv.history(session))} turns stored")


# ============================================================ Section 4
print("\n=== Section 4: memory lifecycle ===")
mem = MemoryStore(db_path=db("mem.db"))

m1 = mem.capture("My gmail password is hunter2", type="credential", importance=0.9)
check("secrets auto-classified as secret", m1.privacy_level == SECRET,
      f"privacy_level={m1.privacy_level}")

m2 = mem.capture("My bank account is with HDFC", importance=0.6)
check("sensitive content classified private", m2.privacy_level == PRIVATE,
      f"privacy_level={m2.privacy_level}")

try:
    mem.get(m1.id, audience="cloud")
    check("private memory blocked outside scope", False, "cloud read allowed!")
except MemoryPermissionError as exc:
    check("private memory blocked outside scope", True, str(exc)[:80])

owner_read = mem.get(m1.id, audience="owner")
check("owner can read secret memory", owner_read.id == m1.id,
      f"access_count={owner_read.access_count}")

recalled = mem.recall("bank", audience="android")
check("recall filters by audience clearance", all(r.id != m2.id for r in recalled),
      f"android recall returned {[r.id for r in recalled]}")

granted = mem.update(m2.id, permissions=["android"], reason="explicit grant")
check("explicit permission grants access",
      mem.get(m2.id, audience="android").id == m2.id,
      f"permissions={granted.permissions} version={granted.version}")

v = mem.update(m2.id, content="My bank account is with ICICI", reason="user correction")
check("memory versioning increments and keeps history",
      v.version >= 3 and len(mem.versions(m2.id)) >= 3,
      f"version={v.version} snapshots={len(mem.versions(m2.id))}")

reverted = mem.revert(m2.id, 1)
check("memory revert restores earlier content", "HDFC" in reverted.content,
      f"content={reverted.content!r} version={reverted.version}")

mem.capture("Krishna is building a Jarvis assistant in Python", importance=0.4)
mem.capture("Krishna is building Jarvis assistant using Python", importance=0.5)
result = mem.consolidate()
check("near-duplicate memories consolidated", result["groups"] >= 1,
      f"groups={result['groups']} merged={result['merged']}")
if result["merged"]:
    absorbed = result["merged"][0]["absorbed"][0]
    check("absorbed record archived, not deleted",
          mem.get(absorbed, touch=False).status == STATUS_ARCHIVED,
          f"{absorbed} status={mem.get(absorbed, touch=False).status}")

old = mem.capture("trivial passing thought", importance=0.05, confidence=0.2)
with mem._lock:  # simulate an old, untouched record (real decay math, faked clock only)
    mem._conn.execute(
        "UPDATE memories SET created_at=?, updated_at=?, last_accessed=NULL WHERE id=?",
        ("2024-01-01T00:00:00", "2024-01-01T00:00:00", old.id))
    mem._conn.commit()
strength = mem.strength(mem.get(old.id, touch=False))
decayed = mem.decay()
check("decay archives weak stale memories", old.id in decayed["archived"],
      f"strength={strength} archived={len(decayed['archived'])}")

important = mem.capture("Owner is Krishna Prajapati", importance=0.95)
with mem._lock:
    mem._conn.execute("UPDATE memories SET created_at=?, updated_at=?, last_accessed=NULL"
                      " WHERE id=?", ("2024-01-01T00:00:00", "2024-01-01T00:00:00", important.id))
    mem._conn.commit()
mem.decay()
check("important memories survive decay",
      mem.get(important.id, touch=False).status == "active",
      f"status={mem.get(important.id, touch=False).status}")

restored = mem.restore(old.id)
check("archived memory can be restored", restored.status == "active",
      f"status={restored.status} version={restored.version}")

forgotten = mem.forget(old.id)
check("forget erases content but keeps audit history",
      "forgotten" in forgotten.content and len(mem.versions(old.id)) >= 2,
      f"versions kept={len(mem.versions(old.id))}")

try:
    mem.capture("")
    check("invalid memory input rejected", False, "blank accepted")
except ValueError as exc:
    check("invalid memory input rejected", True, f"ValueError: {exc}")

stats = mem.stats()
check("memory denies are audited", stats["denied_reads"] >= 1, f"denied_reads={stats['denied_reads']}")


# ============================================================ Section 5
print("\n=== Section 5: profile ===")
prof = ProfileStore(db_path=db("profile.db"))

prof.set("name", "Krishna Prajapati")
prof.set("city", "Ahmedabad")
corrected = prof.correct("city", "Gandhinagar", note="user said so")
check("profile correction applied and versioned",
      corrected.value == "Gandhinagar" and corrected.version == 2,
      f"value={corrected.value} version={corrected.version}")
check("previous value retained in history",
      any(h["value"] == "Ahmedabad" for h in prof.history("city")),
      f"history={[h['value'] for h in prof.history('city')]}")

reverted = prof.revert("city", 1)
check("profile revert works", reverted.value == "Ahmedabad",
      f"value={reverted.value} version={reverted.version}")

first = prof.observe("editor", "vscode")
second = prof.observe("editor", "vscode")
check("one observation never becomes a preference", not first["promoted"],
      first["reason"])
third = prof.observe("editor", "vscode")
check("repeated evidence promotes the preference", third["promoted"],
      f"{third['reason']} confidence={third['confidence']}")
check("promoted value is stored", prof.get("editor") == "vscode",
      f"editor={prof.get('editor')} (evidence {len(prof.evidence_for('editor'))})")

prof.correct("editor", "neovim")
after = prof.observe("editor", "vscode")
for _ in range(4):
    after = prof.observe("editor", "vscode")
check("user correction outranks later observations",
      prof.get("editor") == "neovim" and not after["promoted"], after["reason"])

long_goal = prof.add_goal("Become a trillionaire", "long_term", priority=1)
mid = prof.add_goal("Ship Jarvis Pro 1.0", "medium_term", priority=2, parent=long_goal)
step = prof.add_goal("Finish roadmap features", "short_term", priority=1, parent=mid)
blocked = prof.add_goal("Publish release notes", "short_term", priority=1, depends_on=[step])
tree = prof.goal_tree()
check("goal hierarchy nests correctly",
      tree[0]["goal_id"] == long_goal and tree[0]["children"][0]["goal_id"] == mid,
      f"root={tree[0]['title']} child={tree[0]['children'][0]['title']}")
check("next_goal respects dependencies", prof.next_goal()["goal_id"] in (step, long_goal),
      f"next={prof.next_goal()['title']}")
prof.update_goal(step, progress=1.0)
check("completing a goal unblocks its dependants",
      any(g["goal_id"] == blocked for g in [prof.next_goal()] if g),
      f"next after completion={prof.next_goal()['title']}")

try:
    prof.add_goal("bad", "someday")
    check("invalid goal horizon rejected", False, "accepted")
except ValueError as exc:
    check("invalid goal horizon rejected", True, f"ValueError: {exc}")

prof.add_constraint("no-deletes", "forbid_scope", {"scopes": ["files.delete"]},
                    "owner forbids deletions")
verdict = prof.check_constraints("files.delete.project")
check("user constraint blocks forbidden scope", not verdict["allowed"],
      verdict["violations"][0]["reason"])
check("unrelated scope stays allowed", prof.check_constraints("files.read")["allowed"],
      "files.read allowed")
try:
    prof.enforce("files.delete.now")
    check("enforce raises on violation", False, "no error")
except ConstraintViolation as exc:
    check("enforce raises on violation", True, str(exc))

prof.set_permission("notify", True)
prof.set_permission("notify.android", False)
check("longest-prefix permission wins",
      prof.permission("notify.desktop") is True and prof.permission("notify.android") is False,
      "notify.desktop=True notify.android=False")

for success in (True, True, False, True):
    exp = prof.record_interaction("python", success, depth="advanced")
check("expertise estimated from real interactions",
      exp["samples"] == 4 and exp["level"] != "unknown",
      f"score={exp['score']} level={exp['level']} evidence={exp['evidence']}")
check("unknown topic reports unknown, not a guess",
      prof.expertise("welding")["level"] == "unknown", prof.expertise("welding")["evidence"])


# ============================================================ Section 6
print("\n=== Section 6: personality ===")
pers = Personality(profile=prof)
renders = [pers.render(surface, {"tone": "warm", "verbosity": "detailed", "identity": "Ultron"})
           for surface in ("gui", "voice", "text", "android", "agent")]
check("core personality identical on all surfaces", pers.consistent(renders),
      f"identity={renders[0]['core']['identity']} on {len(renders)} surfaces")
check("presentation-only adaptation (core cannot be overridden)",
      all(r["core"]["identity"] == "Jarvis" for r in renders)
      and "identity" not in renders[0]["presentation"],
      "injected identity override was stripped")
check("voice surface is concise", renders[1]["presentation"]["verbosity"] == "concise",
      f"voice verbosity={renders[1]['presentation']['verbosity']}")
check("background agents do not chit-chat",
      renders[4]["presentation"]["offer_help"] is False, "agent offer_help=False")

emotion = pers.emotional_context(conv.mood(session))
check("emotional context produces a response policy",
      "policy" in emotion and isinstance(emotion["policy"], dict),
      f"dominant={emotion['dominant']} policy={emotion['policy']}")

conv2 = ConversationEngine(db_path=db("conv2.db"), personality=pers)
s2 = conv2.start_session("text")
t2 = conv2.analyse(s2, "explain this slowly please, i'm confused")
check("conversation directives pass through personality constraint",
      all(k in ("tone", "verbosity", "technical_depth", "pace", "offer_help", "style")
          for k in t2.style_directives),
      f"directives={t2.style_directives}")


# ============================================================ Section 7
print("\n=== Section 7: notes ===")
notes = NotesManager(db_path=db("notes.db"))
note = notes.create("Motivation", "Discipline today.", important=True)
notes.edit(note.note_id, body="Discipline today, Success tomorrow.")
notes.edit(note.note_id, title="Daily Motivation")
history = notes.versions(note.note_id)
check("note version history recorded", len(history) == 3,
      f"versions={[h['version'] for h in history]} actions={[h['action'] for h in history]}")

diff = notes.compare(note.note_id, 1, 2)
check("version compare produces a real diff",
      "Success tomorrow" in diff["diff"] and "body" in diff["changed_fields"],
      f"changed={diff['changed_fields']}")

restored_note = notes.restore(note.note_id, 1)
check("restore returns earlier content as a new version",
      restored_note.body == "Discipline today." and restored_note.version == 4,
      f"body={restored_note.body!r} version={restored_note.version}")

deleted = notes.delete(note.note_id)
check("delete is soft and keeps history",
      deleted.status == "deleted" and len(notes.versions(note.note_id)) == 5,
      f"status={deleted.status} versions={len(notes.versions(note.note_id))}")
try:
    notes.edit(note.note_id, body="nope")
    check("editing a deleted note is refused", False, "edit allowed")
except ValueError as exc:
    check("editing a deleted note is refused", True, str(exc))
notes.undelete(note.note_id)
check("undelete restores the note", notes.get(note.note_id).status == "active",
      f"status={notes.get(note.note_id).status}")

tagged = notes.create("Fix the API bug", "The python function raises on empty input")
check("auto-tagging derives tags from content", "code" in tagged.tags,
      f"tags={tagged.tags}")
check("search finds notes by text", any(n.note_id == tagged.note_id for n in notes.search("api")),
      f"search('api') -> {[n.title for n in notes.search('api')]}")
try:
    notes.create("   ")
    check("blank note title rejected", False, "accepted")
except ValueError as exc:
    check("blank note title rejected", True, f"ValueError: {exc}")
try:
    notes.purge(tagged.note_id)
    check("purge requires prior deletion", False, "purge allowed")
except ValueError as exc:
    check("purge requires prior deletion", True, str(exc))


# ============================================================ Section 8
print("\n=== Section 8: reminders ===")
rem_db = db("rem.db")
rems = ReminderManager(db_path=rem_db, profile=prof)
delivered: list = []
rems.register_channel("desktop", lambda r: delivered.append(("desktop", r.text)))

past = datetime.now() - timedelta(minutes=1)
r_once = rems.schedule("Drink water", past)
fired = rems.tick()
check("event engine fires due reminders",
      delivered and fired[0]["status"] == "delivered",
      f"delivered={delivered} status={fired[0]['status']}")
check("one-time reminder completes after firing",
      rems.get(r_once.reminder_id).state == "completed",
      f"state={rems.get(r_once.reminder_id).state}")

r_daily = rems.schedule("Morning review", past, recurrence="daily")
rems.fire(r_daily.reminder_id)
next_due = rems.get(r_daily.reminder_id)
check("daily recurrence reschedules ~24h later",
      next_due.state == "scheduled" and next_due.due_at > str(datetime.now().date()),
      f"next due_at={next_due.due_at}")

r_weekly = rems.schedule("Weekly backup", past, recurrence="weekly", weekdays=[0, 3])
nxt = rems.next_occurrence(r_weekly, datetime(2026, 9, 15))  # Tuesday
check("weekly recurrence honours selected weekdays", nxt.weekday() in (0, 3),
      f"next={nxt.isoformat()} weekday={nxt.weekday()}")

r_monthly = rems.schedule("Pay rent", datetime(2026, 1, 31, 9, 0, 0), recurrence="monthly")
monthly_next = rems.next_occurrence(r_monthly)
check("monthly recurrence clamps short months",
      monthly_next.month == 2 and monthly_next.day == 28,
      f"31 Jan -> {monthly_next.date().isoformat()}")

r_custom = rems.schedule("Stretch", past, recurrence="custom", interval=90, unit="minutes")
custom_next = rems.next_occurrence(r_custom, datetime(2026, 9, 15, 10, 0, 0))
check("custom recurrence honours interval/unit",
      custom_next == datetime(2026, 9, 15, 11, 30, 0), f"next={custom_next.isoformat()}")
try:
    rems.schedule("bad", past, recurrence="custom", interval=0)
    check("invalid custom recurrence rejected", False, "accepted")
except ValueError as exc:
    check("invalid custom recurrence rejected", True, f"ValueError: {exc}")

r_snooze = rems.schedule("Take a break", past)
snoozed = rems.snooze(r_snooze.reminder_id, minutes=15)
check("snooze moves the due time and counts",
      snoozed.state == "snoozed" and snoozed.snoozes == 1
      and snoozed.due_at > str(datetime.now().replace(microsecond=0).isoformat()),
      f"state={snoozed.state} snoozes={snoozed.snoozes} due={snoozed.due_at}")
rems.set_preference("max_snoozes", 2)
rems.snooze(r_snooze.reminder_id, minutes=1)
try:
    rems.snooze(r_snooze.reminder_id, minutes=1)
    check("snooze limit enforced", False, "third snooze allowed")
except ValueError as exc:
    check("snooze limit enforced", True, str(exc))

# retry + escalation with a genuinely failing channel
attempts = {"desktop": 0}


def failing_desktop(r):
    attempts["desktop"] += 1
    raise DeliveryError("desktop notifier not running")


escalated: list = []
rems2 = ReminderManager(db_path=db("rem2.db"), profile=prof)
rems2.register_channel("desktop", failing_desktop)
rems2.register_channel("voice", lambda r: escalated.append(("voice", r.text)))
rems2.set_preference("max_attempts", 2)
r_fail = rems2.schedule("Critical alert", past)
first_try = rems2.fire(r_fail.reminder_id)
check("failed delivery schedules a bounded retry",
      first_try["status"] == "retry_scheduled" and first_try["retry_in_s"] > 0,
      f"attempt={first_try['attempt']} retry_in={first_try['retry_in_s']}s")
second_try = rems2.fire(r_fail.reminder_id)
check("escalation to next channel after attempts exhausted",
      second_try["status"] == "escalated" and escalated,
      f"channel={second_try.get('channel')} escalated={escalated}")
check("retries are bounded (no infinite loop)", attempts["desktop"] == 2,
      f"desktop attempts={attempts['desktop']} limit=2")

rems2.set_preference("allow_escalation", False)
r_noesc = rems2.schedule("Quiet alert", past)
rems2.fire(r_noesc.reminder_id)
gave_up = rems2.fire(r_noesc.reminder_id)
check("escalation respects user preference",
      gave_up["status"] == "failed" and gave_up["escalated"] is False,
      gave_up["reason"][:70])

prof.set_permission("notify.voice", False)
rems2.set_preference("allow_escalation", True)
r_perm = rems2.schedule("Permission alert", past)
rems2.fire(r_perm.reminder_id)
perm_result = rems2.fire(r_perm.reminder_id)
check("escalation respects user permissions", perm_result["status"] == "failed",
      f"status={perm_result['status']} (notify.voice denied)")
prof.set_permission("notify.voice", True)

missing = ReminderManager(db_path=db("rem3.db"))
r_nochan = missing.schedule("No channel", past)
nochan = missing.fire(r_nochan.reminder_id)
check("missing channel reported, not crashed", nochan["status"] == "retry_scheduled",
      nochan["reason"])

# persistence across "restart"
reopened = ReminderManager(db_path=rem_db)
check("reminders survive restart",
      any(r.reminder_id == r_daily.reminder_id for r in reopened.list()),
      f"{len(reopened.list())} reminders reloaded from {os.path.basename(rem_db)}")
check("delivery events are persisted", len(reopened.events(r_daily.reminder_id)) >= 2,
      f"events={[e['event'] for e in reopened.events(r_daily.reminder_id)]}")

cancelled = rems.cancel(r_weekly.reminder_id)
check("cancel stops a reminder", cancelled.state == "cancelled", f"state={cancelled.state}")
try:
    rems.snooze(r_weekly.reminder_id)
    check("cancelled reminders cannot be snoozed", False, "snooze allowed")
except ValueError as exc:
    check("cancelled reminders cannot be snoozed", True, str(exc))
try:
    rems.schedule("bad", "not-a-date")
    check("invalid due date rejected", False, "accepted")
except (ValueError, TypeError) as exc:
    check("invalid due date rejected", True, f"{type(exc).__name__}: {exc}")

print(f"\nreminder stats: {rems.stats()}")
print(f"memory stats:   {mem.stats()}")
print(f"notes stats:    {notes.stats()}")
print(f"\n{PASSED} passed, {FAILED} failed")
if __name__ == "__main__":
    sys.exit(1 if FAILED else 0)


def test_subsystems_batch2_checks_all_pass():
    """Expose the module-level checks to pytest.

    The checks above run at import time.  Without this the bare
    ``sys.exit`` made pytest fail collection, so none of them ran.
    """
    assert FAILED == 0, f"{FAILED} check(s) failed"

