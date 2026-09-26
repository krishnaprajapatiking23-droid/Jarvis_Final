"""
Batch 3d behavioural tests.

S22  knowledge graph with provenance
S26  automatic recovery
S27  corruption detection

Every check exercises the real implementation against real files and real
SQLite databases. Nothing is mocked and nothing passes without evidence.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.knowledge_graph import (ACTIVE, RETRACTED, SUPERSEDED,
                                         KnowledgeGraph)
from jarvis_core.recovery import (BAD_JSON, CORRUPT, EMPTY, MISSING, OK,
                                  REBUILT, REPAIRED, RESTORED, STALE_JOURNAL,
                                  RecoveryManager)

PASSED = 0
FAILED = 0


def check(label, condition, evidence=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"[PASS] {label}  {evidence}")
    else:
        FAILED += 1
        print(f"[FAIL] {label}  {evidence}")


def section(name):
    print(f"\n=== {name} ===")


TMP = tempfile.mkdtemp(prefix="jarvis3d_")


# =====================================================================
section("S22 knowledge graph: nodes, edges, provenance")

kg = KnowledgeGraph(os.path.join(TMP, "kg.db"))

bad = kg.add_node("   ", "person")
check("a nameless node is refused",
      bad["status"] == "invalid_input", bad["error"])

bad_conf = kg.add_node("Nova", "person", confidence="very sure")
check("a non-numeric confidence is refused",
      bad_conf["status"] == "invalid_input", bad_conf["error"])

owner = kg.add_node("Krishna Prajapati", "person",
                    attrs={"role": "owner", "city": "Gujarat"},
                    source="owner", author="krishna", confidence=0.95,
                    trace_id="JRV-3D-1", note="stated directly by the owner")
check("a node is created with provenance",
      owner["status"] == "ok" and owner["created"] and owner["claim_id"].startswith("KC-"),
      f"id={owner['id']} claim={owner['claim_id']}")

again = kg.add_node("krishna  PRAJAPATI", "person", attrs={"focus": "jarvis"},
                    source="owner", author="krishna", confidence=0.9)
check("the same entity written differently is merged, not duplicated",
      again["status"] == "ok" and not again["created"] and again["id"] == owner["id"],
      f"same id={again['id']}")

merged = kg.get_node("Krishna Prajapati")
check("merging keeps old attributes and adds new ones",
      merged["attrs"]["role"] == "owner" and merged["attrs"]["focus"] == "jarvis",
      f"attrs={merged['attrs']}")

claims = kg.provenance(owner["id"])
check("every write leaves its own claim behind",
      len(claims) == 2 and all(c["author"] == "krishna" for c in claims),
      f"{len(claims)} claims, sources={[c['source'] for c in claims]}")
check("a claim records source, confidence and trace",
      any(c["trace_id"] == "JRV-3D-1" and c["confidence"] == 0.95 for c in claims),
      "trace JRV-3D-1 confidence 0.95 stored")

rel = kg.relate("Krishna Prajapati", "works on", "Jarvis Pro",
                source="owner", author="krishna", confidence=0.9,
                trace_id="JRV-3D-2")
check("a relationship is asserted and its missing node auto-created",
      rel["status"] == "ok" and kg.get_node("Jarvis Pro") is not None,
      rel["statement"])

no_rel = kg.relate("Jarvis Pro", "depends_on", "Unknown Thing", create_missing=False)
check("strict mode will not invent nodes it has never heard of",
      no_rel["status"] == "not_found", no_rel["error"])

self_rel = kg.relate("Jarvis Pro", "depends_on", "jarvis pro")
check("a node cannot be related to itself",
      self_rel["status"] == "invalid_input", self_rel["error"])

nameless = kg.relate("Krishna Prajapati", "  ", "Jarvis Pro")
check("a relationship needs a relation name",
      nameless["status"] == "invalid_input", nameless["error"])

repeat = kg.relate("Krishna Prajapati", "works on", "Jarvis Pro",
                   source="tool", confidence=0.6)
check("re-asserting a fact adds a claim instead of a duplicate edge",
      repeat["status"] == "ok" and not repeat["created"]
      and len(kg.provenance(repeat["id"])) == 2,
      f"edge {repeat['id']} now has {len(kg.provenance(repeat['id']))} claims")


# =====================================================================
section("S22 conflicting claims and trust")

kg.relate("Jarvis Pro", "status_is", "in development",
          source="owner", confidence=0.9)
weak = kg.relate("Jarvis Pro", "status_is", "abandoned",
                 source="model", confidence=0.4)
check("a weak source cannot overwrite a stronger single-valued fact",
      weak["status"] == "conflict", weak["error"])
check("the trusted fact is still the one on record",
      weak["existing_target"] == "in development",
      f"still status_is '{weak['existing_target']}'")

strong = kg.relate("Jarvis Pro", "status_is", "shipping",
                   source="owner", author="krishna", confidence=0.99,
                   note="owner corrected the status")
check("a stronger source supersedes the old fact",
      strong["status"] == "ok" and strong.get("superseded"),
      f"superseded={strong['superseded']}")

active_status = [e["other_name"] for e in kg.edges_of(kg.get_node("Jarvis Pro")["id"],
                                                      relation="status_is")]
check("only one value of a single-valued relation stays active",
      active_status == ["shipping"], f"active status_is={active_status}")
check("the superseded claim is kept for audit, not deleted",
      any(c["status"] == SUPERSEDED
          for c in kg.provenance(strong["superseded"][0], include_retracted=True)),
      "old claim marked superseded")
check("no contradictions remain after supersession",
      kg.contradictions() == [], "0 contradictions")


# =====================================================================
section("S22 traversal and explanation")

kg.relate("Jarvis Pro", "uses", "SQLite", source="tool", confidence=0.85)
kg.relate("SQLite", "is_a", "database", source="document", confidence=0.8)

nb = kg.neighbours("Krishna Prajapati", depth=1)
check("one-hop neighbours are real edges",
      nb["status"] == "ok" and [n["name"] for n in nb["neighbours"]] == ["Jarvis Pro"],
      f"neighbours={[n['name'] for n in nb['neighbours']]}")

deep = kg.neighbours("Krishna Prajapati", depth=3)
names = sorted(n["name"] for n in deep["neighbours"])
check("multi-hop traversal reaches indirect knowledge",
      "SQLite" in names and "database" in names,
      f"depth 3 reached {names}")

missing_nb = kg.neighbours("Nobody At All")
check("traversal from an unknown node is not_found",
      missing_nb["status"] == "not_found", missing_nb["error"])

path = kg.path("Krishna Prajapati", "database")
check("a relationship chain is found between distant nodes",
      path["status"] == "ok" and path["hops"] == 3,
      f"{path['hops']} hops: {' -> '.join(path['path'])}")

kg.add_node("Orphan Island", "place", source="document", confidence=0.5)
no_path = kg.path("Krishna Prajapati", "Orphan Island")
check("an unconnected node reports no chain instead of guessing",
      no_path["status"] == "not_found", no_path["error"])

explained = kg.explain("Jarvis Pro")
check("the graph can explain why it believes each fact",
      explained["status"] == "ok" and explained["fact_count"] >= 3
      and all(f["source"] != "" for f in explained["facts"]),
      f"{explained['fact_count']} facts, sources="
      f"{sorted({f['source'] for f in explained['facts']})}")

unknown_explain = kg.explain("Atlantis")
check("explaining an unknown entity is not_found, never invented",
      unknown_explain["status"] == "not_found", unknown_explain["error"])


# =====================================================================
section("S22 retraction, persistence and pipeline entry")

island = kg.get_node("Orphan Island")
retracted = kg.retract(island["id"], reason="never existed")
check("a node can be withdrawn with a reason",
      retracted["status"] == "ok", f"{retracted['kind']} {retracted['retracted']}")
check("a retracted node disappears from active knowledge",
      all(n["name"] != "Orphan Island" for n in kg.nodes()),
      "not listed as active")
check("its claims survive for audit",
      any(c["status"] == RETRACTED
          for c in kg.provenance(island["id"], include_retracted=True)),
      "claim marked retracted, not deleted")

missing_retract = kg.retract("KN-doesnotexist")
check("retracting an unknown id is not_found",
      missing_retract["status"] == "not_found", missing_retract["error"])

before = kg.stats()
kg2 = KnowledgeGraph(os.path.join(TMP, "kg.db"))
after = kg2.stats()
check("the whole graph survives a restart",
      after["nodes"] == before["nodes"] and after["claims"] == before["claims"],
      f"{after['nodes']} nodes, {after['edges']} edges, {after['claims']} claims reloaded")

via_run = kg2.run("explain", name="SQLite")
check("the graph is callable through its pipeline entry point",
      via_run["status"] == "ok" and via_run["fact_count"] >= 1,
      f"explain(SQLite) -> {via_run['fact_count']} fact(s)")

bad_action = kg2.run("telepathy")
check("an unknown knowledge action is invalid input",
      bad_action["status"] == "invalid_input", bad_action["error"])

bad_args = kg2.run("path", start="SQLite")
check("bad arguments are reported, not crashed on",
      bad_args["status"] == "invalid_input", bad_args["error"])

health = kg2.health()
check("the graph reports real health",
      health["available"] and health["nodes"] >= 4,
      f"nodes={health['nodes']} edges={health['edges']} "
      f"avg_confidence={health['avg_confidence']}")


# =====================================================================
section("S27 corruption detection")

DATA = os.path.join(TMP, "state")
os.makedirs(DATA, exist_ok=True)
rec = RecoveryManager(os.path.join(DATA, "recovery.db"), data_dir=DATA)

good_db = os.path.join(DATA, "good.db")
conn = sqlite3.connect(good_db)
conn.execute("CREATE TABLE t (a TEXT)")
conn.execute("INSERT INTO t VALUES ('hello')")
conn.commit()
conn.close()

good_json = os.path.join(DATA, "config.json")
with open(good_json, "w", encoding="utf-8") as fh:
    json.dump({"mode": "standard"}, fh)

healthy = rec.check_sqlite(good_db)
check("a healthy database passes a real integrity check",
      healthy["status"] == OK and healthy["integrity"] == "ok" and healthy["tables"] == 1,
      f"tables={healthy['tables']} bytes={healthy['bytes']}")

check("a healthy JSON file is parsed, not assumed",
      rec.check_json(good_json)["status"] == OK, "config.json parses")

missing = rec.check_sqlite(os.path.join(DATA, "nope.db"))
check("a missing database is reported as missing",
      missing["status"] == "not_found" and missing["problem"] == MISSING,
      missing["error"])

empty_db = os.path.join(DATA, "empty.db")
open(empty_db, "wb").close()
empty = rec.check_sqlite(empty_db)
check("a zero-byte database is caught",
      empty["status"] == "corrupt" and empty["problem"] == EMPTY, empty["error"])

trash_db = os.path.join(DATA, "trash.db")
with open(trash_db, "wb") as fh:
    fh.write(b"this is not a database at all\x00\xff")
trash = rec.check_sqlite(trash_db)
check("a file with a broken header is caught before SQLite is trusted",
      trash["status"] == "corrupt" and trash["problem"] == CORRUPT, trash["error"])

torn_db = os.path.join(DATA, "torn.db")
torn_conn = sqlite3.connect(torn_db)
torn_conn.execute("CREATE TABLE big (a TEXT)")
torn_conn.executemany("INSERT INTO big VALUES (?)",
                      [(f"row-{i}-{'x' * 80}",) for i in range(2000)])
torn_conn.commit()
torn_conn.close()
pages = os.path.getsize(torn_db) // 4096
with open(torn_db, "r+b") as fh:
    fh.seek(4096 * (pages // 2))          # overwrite a real data page, keep the header
    fh.write(b"\xAA" * 4096 * 3)
torn = rec.check_sqlite(torn_db)
check("a page-level corrupted database fails integrity_check",
      torn["status"] in ("corrupt", "unavailable"),
      f"{torn['status']}: {str(torn.get('error', torn))[:80]}")

broken_json = os.path.join(DATA, "broken.json")
with open(broken_json, "w", encoding="utf-8") as fh:
    fh.write('{"mode": "standard",}')
bj = rec.check_json(broken_json)
check("invalid JSON is located precisely",
      bj["status"] == "corrupt" and bj["problem"] == BAD_JSON, bj["error"])

check("a check without a path is invalid input",
      rec.check_json("")["status"] == "invalid_input", "empty path refused")

scan = rec.scan()
damaged_names = sorted(d["name"] for d in scan["damaged"])
check("a scan separates healthy state from damaged state",
      scan["status"] == "degraded" and "good.db" in scan["healthy"]
      and {"empty.db", "trash.db", "broken.json"} <= set(damaged_names),
      f"healthy={sorted(scan['healthy'])} damaged={damaged_names}")
check("the recovery database itself is excluded from its own scan",
      "recovery.db" not in scan["healthy"] + damaged_names,
      "recovery.db not scanned")

journal = good_db + "-journal"
with open(journal, "wb") as fh:
    fh.write(b"leftover")
stale = rec.scan([good_db])
check("a leftover journal is detected as a risk on a healthy database",
      stale["damaged"] and stale["damaged"][0]["problem"] == STALE_JOURNAL,
      stale["damaged"][0]["error"])


# =====================================================================
section("S26 automatic recovery")

cleared = rec.repair(good_db, problem=STALE_JOURNAL)
check("a stale journal is cleared and re-verified",
      cleared["status"] == REPAIRED and cleared["verified"]
      and not os.path.exists(journal),
      f"action={cleared['action']} journal removed")

bk = rec.backup(good_db)
check("a healthy file can be backed up",
      bk["status"] == OK and os.path.exists(bk["backup"]),
      f"{os.path.basename(bk['backup'])} ({bk['bytes']} bytes)")

refused = rec.backup(trash_db)
check("a damaged file is never backed up over a good one",
      refused["status"] == "failed", refused["error"][:80])

check("backing up a non-existent file is not_found",
      rec.backup(os.path.join(DATA, "ghost.db"))["status"] == "not_found",
      "ghost.db not found")

for _ in range(4):
    rec.backup(good_db)
kept = len([p for p in os.listdir(rec.backup_dir) if p.startswith("good.db.")])
check("backups rotate instead of growing forever",
      kept == 3, f"{kept} backups kept (max 3)")

# now really corrupt the live database and recover it from backup
with open(good_db, "r+b") as fh:
    fh.seek(0)
    fh.write(b"DESTROYED HEADER")
check("the live database is genuinely broken before recovery",
      rec.check_sqlite(good_db)["status"] == "corrupt", "header destroyed")

restored = rec.repair(good_db)
check("a corrupt database is restored from its newest healthy backup",
      restored["status"] == RESTORED and restored["verified"],
      f"action={restored['action']} verified={restored['verified']}")
with sqlite3.connect(good_db) as verify:
    rows = verify.execute("SELECT a FROM t").fetchall()
check("the restored database still holds the original data",
      rows == [("hello",)], f"rows={rows}")
check("the damaged copy is quarantined, not deleted",
      restored["quarantined"] and os.path.exists(restored["quarantined"]),
      os.path.basename(restored["quarantined"]))

no_backup = rec.repair(trash_db, rebuild=False)
check("without a backup and without permission to rebuild, repair fails honestly",
      no_backup["status"] == "failed", no_backup["error"])
check("the failed repair left the file untouched",
      os.path.exists(trash_db), "trash.db still present")

rebuilt = rec.repair(broken_json)
check("unrecoverable JSON is rebuilt to empty state and flagged as data loss",
      rebuilt["status"] == REBUILT and rebuilt["verified"] and rebuilt["data_loss"],
      f"action={rebuilt['action']} quarantined="
      f"{os.path.basename(rebuilt['quarantined'])}")
check("the rebuilt file is valid JSON",
      json.load(open(broken_json, encoding="utf-8")) == {}, "parses as {}")

full = rec.recover()
check("recover() repairs everything it can and re-scans to prove it",
      full["status"] == OK and not full["still_damaged"],
      f"repaired={[r['resource'] for r in full['repaired']]} "
      f"still_damaged={len(full['still_damaged'])}")

clean = rec.recover()
check("a healthy system needs no repairs",
      clean["status"] == OK and clean["repaired"] == [], clean["message"])

log = rec.incidents()
actions = sorted({i["action"] for i in log})
check("every recovery action is recorded with its outcome",
      {"clear_journal", "restore_backup", "rebuild"} <= set(actions),
      f"actions={actions}")
check("verified repairs are distinguishable from failures",
      any(i["verified"] == 1 for i in log) and any(i["outcome"] == "failed" for i in log),
      f"{sum(i['verified'] for i in log)} verified of {len(log)} incidents")

rec2 = RecoveryManager(os.path.join(DATA, "recovery.db"), data_dir=DATA)
check("the incident history survives a restart",
      len(rec2.incidents()) == len(log), f"{len(rec2.incidents())} incidents reloaded")

stats = rec2.stats()
check("recovery statistics come from stored incidents",
      stats["incidents"] == len(log) and stats["quarantined"] >= 2,
      f"incidents={stats['incidents']} quarantined={stats['quarantined']} "
      f"by_outcome={stats['by_outcome']}")

bad_recovery_action = rec2.run("reformat_everything")
check("an unknown recovery action is invalid input",
      bad_recovery_action["status"] == "invalid_input", bad_recovery_action["error"])


# =====================================================================
section("kernel integration")

from jarvis_core.kernel import Kernel

KDATA = os.path.join(TMP, "kernel_data")
os.makedirs(KDATA, exist_ok=True)
kernel = Kernel(data_dir=KDATA)

check("the kernel owns a knowledge graph and a recovery manager",
      isinstance(kernel.knowledge, KnowledgeGraph)
      and isinstance(kernel.recovery_manager, RecoveryManager),
      "kernel.knowledge and kernel.recovery_manager present")

sel_k = kernel.managers.select("knowledge")
sel_r = kernel.managers.select("recovery")
check("both subsystems are selectable through the manager registry",
      sel_k["manager"] == "knowledge" and sel_r["manager"] == "recovery",
      f"{sel_k['manager']}/{sel_k['status']}, {sel_r['manager']}/{sel_r['status']}")

live = kernel.knowledge.run("relate", source_name="Krishna", relation="owns",
                            target_name="Jarvis", source="owner",
                            author="krishna", confidence=0.95,
                            trace_id="JRV-KERNEL")
check("knowledge can be written through the live kernel",
      live["status"] == "ok", live["statement"])

kclaims = kernel.knowledge.provenance(live["id"])
check("kernel-written knowledge carries the request trace",
      kclaims and kclaims[0]["trace_id"] == "JRV-KERNEL",
      f"trace={kclaims[0]['trace_id']} source={kclaims[0]['source']}")

kscan = kernel.recovery_manager.run("scan")
check("the kernel can scan its own live state files",
      kscan["status"] in (OK, "degraded") and kscan["checked"] >= 5,
      f"checked={kscan['checked']} damaged={kscan['damaged_count']}")

khealth = kernel.health()
check("kernel health reports knowledge and recovery state",
      khealth["knowledge"]["available"] and khealth["recovery"]["available"],
      f"knowledge nodes={khealth['knowledge']['nodes']} "
      f"recovery resources={khealth['recovery']['resources']}")

# a real repair through the kernel must show up in analytics
stray = os.path.join(KDATA, "stray.json")
with open(stray, "w", encoding="utf-8") as fh:
    fh.write("{not json")
krepair = kernel.recovery_manager.run("repair", path=stray)
check("the kernel repairs its own damaged state file",
      krepair["status"] in (REBUILT, RESTORED, REPAIRED) and krepair["verified"],
      f"{os.path.basename(stray)} -> {krepair['status']}")

# analytics.success_rate() returns the rate itself; the rows come from scores()
rate = kernel.analytics.success_rate("recovery")
rows = kernel.analytics.scores("recovery")
check("recovery activity is visible to analytics",
      rate is not None and rows and sum(r["uses"] for r in rows) >= 1,
      f"recovery events={sum(r['uses'] for r in rows)} "
      f"actions={[r['name'] for r in rows]} success_rate={rate}")


print(f"\n{PASSED} passed, {FAILED} failed")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILED else 0)
