"""
==========================================
JARVIS PRO - Knowledge graph with provenance
==========================================

Roadmap section 22.

A project-wide grep showed no knowledge graph existed anywhere in Jarvis
(`jarvis_core/graph.py` is the task *dependency* graph, a different thing), so
this is a new subsystem rather than a duplicate.

What it stores
    nodes        entities Jarvis knows about (people, projects, tools, facts)
    edges        typed relationships between nodes
    provenance   for every node and edge: where the claim came from, who said
                 it, when, with what confidence and under which trace

Every write is a *claim*. Nothing enters the graph without provenance, so any
answer derived from the graph can be explained ("I believe X because ...").

Failure modes are explicit: ok / invalid_input / not_found / conflict /
unavailable. Nothing is silently swallowed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# claim status
ACTIVE = "active"
RETRACTED = "retracted"
SUPERSEDED = "superseded"

# trust ordering for sources: a stronger source may overwrite a weaker one
SOURCE_TRUST = {
    "owner": 1.0,
    "user": 1.0,
    "verification": 0.9,
    "tool": 0.8,
    "document": 0.7,
    "web": 0.6,
    "inference": 0.5,
    "model": 0.45,
    "unknown": 0.3,
}

# relations where a subject may only have ONE object at a time; a second
# different object is a contradiction rather than an extra fact
UNIQUE_RELATIONS = {"is_a", "located_in", "owned_by", "status_is", "born_on"}

MAX_PATH_DEPTH = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _short(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _key(name: str) -> str:
    """Canonical lookup key so 'Krishna  Prajapati' == 'krishna prajapati'."""
    return " ".join(str(name).strip().lower().split())


@dataclass
class Claim:
    """Provenance for one assertion in the graph."""

    id: str
    subject_kind: str          # "node" | "edge"
    subject_id: str
    source: str
    author: str
    confidence: float
    trace_id: str
    note: str = ""
    created_at: str = field(default_factory=_now)
    status: str = ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class KnowledgeGraph:
    """Typed graph of what Jarvis knows, with a provenance trail per claim."""

    capability = "knowledge"

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None) -> None:
        self.kernel = kernel
        if db_path is None:
            os.makedirs(_DEF_DIR, exist_ok=True)
            db_path = os.path.join(_DEF_DIR, "knowledge.db")
        else:
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ------------------------------------------------ storage

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    key TEXT UNIQUE,
                    name TEXT,
                    type TEXT,
                    attrs TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    relation TEXT,
                    target_id TEXT,
                    weight REAL,
                    attrs TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY,
                    subject_kind TEXT,
                    subject_id TEXT,
                    source TEXT,
                    author TEXT,
                    confidence REAL,
                    trace_id TEXT,
                    note TEXT,
                    created_at TEXT,
                    status TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_edge_src ON edges(source_id, relation);
                CREATE INDEX IF NOT EXISTS idx_edge_tgt ON edges(target_id, relation);
                CREATE INDEX IF NOT EXISTS idx_claim_subj ON claims(subject_kind, subject_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_edge_triple
                    ON edges(source_id, relation, target_id);
                """
            )

    # ------------------------------------------------ provenance

    def _record_claim(self, kind: str, subject_id: str, *, source: str, author: str,
                      confidence: float, trace_id: str, note: str) -> Claim:
        claim = Claim(
            id=_short("KC"),
            subject_kind=kind,
            subject_id=subject_id,
            source=source,
            author=author,
            confidence=float(confidence),
            trace_id=trace_id or "-",
            note=note or "",
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                (claim.id, claim.subject_kind, claim.subject_id, claim.source,
                 claim.author, claim.confidence, claim.trace_id, claim.note,
                 claim.created_at, claim.status),
            )
        return claim

    def provenance(self, subject_id: str, *, include_retracted: bool = False) -> list[dict[str, Any]]:
        """Every claim ever made about a node or edge, newest first."""
        sql = "SELECT * FROM claims WHERE subject_id = ?"
        params: list[Any] = [subject_id]
        if not include_retracted:
            sql += " AND status = ?"
            params.append(ACTIVE)
        sql += " ORDER BY created_at DESC, rowid DESC"
        with self._lock, self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def explain(self, name: str) -> dict[str, Any]:
        """Human-readable justification for everything known about a node."""
        node = self.get_node(name)
        if not node:
            return {"status": "not_found", "error": f"nothing is known about '{name}'"}
        facts = []
        for edge in self.edges_of(node["id"]):
            claims = self.provenance(edge["id"])
            best = claims[0] if claims else {}
            facts.append({
                "statement": f"{node['name']} {edge['relation']} {edge['other_name']}",
                "direction": edge["direction"],
                "source": best.get("source", "unknown"),
                "author": best.get("author", "unknown"),
                "confidence": best.get("confidence", 0.0),
                "trace_id": best.get("trace_id", "-"),
                "observed_at": best.get("created_at", edge["created_at"]),
            })
        node_claims = self.provenance(node["id"])
        return {
            "status": "ok",
            "node": node,
            "known_because": node_claims,
            "facts": facts,
            "fact_count": len(facts),
        }

    # ------------------------------------------------ nodes

    def add_node(self, name: str, node_type: str = "thing", *, attrs: Optional[dict] = None,
                 source: str = "unknown", author: str = "jarvis", confidence: float = 0.7,
                 trace_id: str = "", note: str = "") -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            return {"status": "invalid_input", "error": "a node needs a non-empty name"}
        if not isinstance(node_type, str) or not node_type.strip():
            return {"status": "invalid_input", "error": "a node needs a type"}
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            return {"status": "invalid_input", "error": "confidence must be a number between 0 and 1"}
        key = _key(name)
        payload = json.dumps(attrs or {}, default=str)
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE key = ?", (key,)).fetchone()
            if row:
                merged = json.loads(row["attrs"] or "{}")
                merged.update(attrs or {})
                conn.execute(
                    "UPDATE nodes SET type = ?, attrs = ?, status = ?, updated_at = ? WHERE id = ?",
                    (node_type or row["type"], json.dumps(merged, default=str), ACTIVE,
                     _now(), row["id"]),
                )
                node_id, created = row["id"], False
            else:
                node_id, created = _short("KN"), True
                conn.execute(
                    "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)",
                    (node_id, key, name.strip(), node_type, payload, ACTIVE, _now(), _now()),
                )
        claim = self._record_claim("node", node_id, source=source, author=author,
                                   confidence=confidence, trace_id=trace_id, note=note)
        return {"status": "ok", "id": node_id, "created": created,
                "name": name.strip(), "type": node_type, "claim_id": claim.id}

    def get_node(self, name_or_id: str) -> Optional[dict[str, Any]]:
        if not isinstance(name_or_id, str) or not name_or_id.strip():
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ? OR key = ?",
                (name_or_id, _key(name_or_id)),
            ).fetchone()
        if not row:
            return None
        node = dict(row)
        node["attrs"] = json.loads(node.get("attrs") or "{}")
        return node

    def nodes(self, node_type: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM nodes WHERE status = ?"
        params: list[Any] = [ACTIVE]
        if node_type:
            sql += " AND type = ?"
            params.append(node_type)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock, self._connect() as conn:
            out = []
            for row in conn.execute(sql, params):
                item = dict(row)
                item["attrs"] = json.loads(item.get("attrs") or "{}")
                out.append(item)
        return out

    # ------------------------------------------------ edges

    def relate(self, source_name: str, relation: str, target_name: str, *,
               weight: float = 1.0, attrs: Optional[dict] = None,
               source: str = "unknown", author: str = "jarvis", confidence: float = 0.7,
               trace_id: str = "", note: str = "", create_missing: bool = True) -> dict[str, Any]:
        """Assert `source_name --relation--> target_name` with provenance."""
        if not isinstance(relation, str) or not relation.strip():
            return {"status": "invalid_input", "error": "a relationship needs a relation name"}
        relation = _key(relation).replace(" ", "_")
        src = self.get_node(source_name)
        tgt = self.get_node(target_name)
        if src is None:
            if not create_missing:
                return {"status": "not_found", "error": f"unknown node '{source_name}'"}
            made = self.add_node(source_name, source=source, author=author,
                                 confidence=confidence, trace_id=trace_id)
            if made["status"] != "ok":
                return made
            src = self.get_node(source_name)
        if tgt is None:
            if not create_missing:
                return {"status": "not_found", "error": f"unknown node '{target_name}'"}
            made = self.add_node(target_name, source=source, author=author,
                                 confidence=confidence, trace_id=trace_id)
            if made["status"] != "ok":
                return made
            tgt = self.get_node(target_name)
        if src["id"] == tgt["id"]:
            return {"status": "invalid_input",
                    "error": f"'{src['name']}' cannot be related to itself"}

        conflict = None
        if relation in UNIQUE_RELATIONS:
            conflict = self._unique_conflict(src["id"], relation, tgt["id"], source, confidence)
            if conflict and conflict["status"] == "conflict":
                return conflict

        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM edges WHERE source_id = ? AND relation = ? AND target_id = ?",
                (src["id"], relation, tgt["id"]),
            ).fetchone()
            if row:
                edge_id, created = row["id"], False
                conn.execute(
                    "UPDATE edges SET weight = ?, status = ?, updated_at = ? WHERE id = ?",
                    (float(weight), ACTIVE, _now(), edge_id),
                )
            else:
                edge_id, created = _short("KE"), True
                conn.execute(
                    "INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?)",
                    (edge_id, src["id"], relation, tgt["id"], float(weight),
                     json.dumps(attrs or {}, default=str), ACTIVE, _now(), _now()),
                )
        claim = self._record_claim("edge", edge_id, source=source, author=author,
                                    confidence=confidence, trace_id=trace_id, note=note)
        result = {"status": "ok", "id": edge_id, "created": created,
                  "statement": f"{src['name']} {relation} {tgt['name']}",
                  "claim_id": claim.id}
        if conflict:
            result["superseded"] = conflict.get("superseded")
        return result

    def _unique_conflict(self, source_id: str, relation: str, target_id: str,
                         source: str, confidence: float) -> Optional[dict[str, Any]]:
        """Handle a second, different object for a single-valued relation.

        A more trusted source supersedes the old edge; a weaker or equal source
        is reported as a conflict instead of quietly corrupting the graph.
        """
        with self._lock, self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM edges WHERE source_id = ? AND relation = ? "
                "AND target_id != ? AND status = ?",
                (source_id, relation, target_id, ACTIVE),
            )]
        if not rows:
            return None
        new_trust = SOURCE_TRUST.get(source, SOURCE_TRUST["unknown"]) * float(confidence)
        superseded = []
        for row in rows:
            claims = self.provenance(row["id"])
            best = claims[0] if claims else {}
            old_trust = (SOURCE_TRUST.get(best.get("source", "unknown"), SOURCE_TRUST["unknown"])
                         * float(best.get("confidence", 0.5)))
            if new_trust <= old_trust:
                other = self.get_node(row["target_id"]) or {"name": row["target_id"]}
                return {
                    "status": "conflict",
                    "error": (f"'{relation}' already points to '{other['name']}' from a "
                              f"stronger source ({best.get('source', 'unknown')}, "
                              f"trust {old_trust:.2f} >= {new_trust:.2f})"),
                    "existing_edge": row["id"],
                    "existing_target": other["name"],
                }
            superseded.append(row["id"])
        with self._lock, self._connect() as conn:
            for edge_id in superseded:
                conn.execute("UPDATE edges SET status = ?, updated_at = ? WHERE id = ?",
                             (SUPERSEDED, _now(), edge_id))
                conn.execute("UPDATE claims SET status = ? WHERE subject_id = ?",
                             (SUPERSEDED, edge_id))
        return {"status": "ok", "superseded": superseded}

    def edges_of(self, node_id: str, *, relation: str = "") -> list[dict[str, Any]]:
        """Active edges touching a node, in both directions."""
        sql = ("SELECT e.*, "
               "(SELECT name FROM nodes WHERE id = e.source_id) AS source_name, "
               "(SELECT name FROM nodes WHERE id = e.target_id) AS target_name "
               "FROM edges e WHERE (e.source_id = ? OR e.target_id = ?) AND e.status = ?")
        params: list[Any] = [node_id, node_id, ACTIVE]
        if relation:
            sql += " AND e.relation = ?"
            params.append(_key(relation).replace(" ", "_"))
        with self._lock, self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params)]
        for row in rows:
            outgoing = row["source_id"] == node_id
            row["direction"] = "out" if outgoing else "in"
            row["other_id"] = row["target_id"] if outgoing else row["source_id"]
            row["other_name"] = row["target_name"] if outgoing else row["source_name"]
        return rows

    def neighbours(self, name: str, *, relation: str = "", depth: int = 1) -> dict[str, Any]:
        node = self.get_node(name)
        if not node:
            return {"status": "not_found", "error": f"unknown node '{name}'"}
        try:
            depth = max(1, min(MAX_PATH_DEPTH, int(depth)))
        except (TypeError, ValueError):
            return {"status": "invalid_input", "error": "depth must be a whole number"}
        seen = {node["id"]}
        frontier = [node["id"]]
        found: list[dict[str, Any]] = []
        for hop in range(1, depth + 1):
            nxt: list[str] = []
            for current in frontier:
                for edge in self.edges_of(current, relation=relation):
                    if edge["other_id"] in seen:
                        continue
                    seen.add(edge["other_id"])
                    nxt.append(edge["other_id"])
                    found.append({"name": edge["other_name"], "relation": edge["relation"],
                                  "direction": edge["direction"], "hops": hop,
                                  "edge_id": edge["id"]})
            frontier = nxt
            if not frontier:
                break
        return {"status": "ok", "node": node["name"], "depth": depth,
                "neighbours": found, "count": len(found)}

    def path(self, start: str, end: str, *, max_depth: int = MAX_PATH_DEPTH) -> dict[str, Any]:
        """Shortest relationship chain between two nodes (breadth-first)."""
        a = self.get_node(start)
        b = self.get_node(end)
        if not a or not b:
            missing = start if not a else end
            return {"status": "not_found", "error": f"unknown node '{missing}'"}
        if a["id"] == b["id"]:
            return {"status": "ok", "hops": 0, "path": [a["name"]], "steps": []}
        max_depth = max(1, min(MAX_PATH_DEPTH, int(max_depth)))
        queue: list[tuple[str, list[dict[str, Any]]]] = [(a["id"], [])]
        seen = {a["id"]}
        while queue:
            current, steps = queue.pop(0)
            if len(steps) >= max_depth:
                continue
            for edge in self.edges_of(current):
                if edge["other_id"] in seen:
                    continue
                trail = steps + [{"from": edge["source_name"], "relation": edge["relation"],
                                  "to": edge["target_name"], "edge_id": edge["id"]}]
                if edge["other_id"] == b["id"]:
                    chain = [a["name"]]
                    for step in trail:
                        chain.append(step["to"] if step["from"] == chain[-1] else step["from"])
                    return {"status": "ok", "hops": len(trail), "path": chain, "steps": trail}
                seen.add(edge["other_id"])
                queue.append((edge["other_id"], trail))
        return {"status": "not_found",
                "error": f"no relationship chain from '{a['name']}' to '{b['name']}' "
                         f"within {max_depth} hops"}

    # ------------------------------------------------ maintenance

    def retract(self, subject_id: str, reason: str = "") -> dict[str, Any]:
        """Withdraw a node or edge and mark its claims retracted (never deleted)."""
        if not isinstance(subject_id, str) or not subject_id.strip():
            return {"status": "invalid_input", "error": "an id is required"}
        with self._lock, self._connect() as conn:
            node = conn.execute("SELECT id FROM nodes WHERE id = ?", (subject_id,)).fetchone()
            edge = conn.execute("SELECT id FROM edges WHERE id = ?", (subject_id,)).fetchone()
            if not node and not edge:
                return {"status": "not_found", "error": f"no node or edge with id '{subject_id}'"}
            table = "nodes" if node else "edges"
            conn.execute(f"UPDATE {table} SET status = ?, updated_at = ? WHERE id = ?",
                         (RETRACTED, _now(), subject_id))
            if node:
                conn.execute(
                    "UPDATE edges SET status = ?, updated_at = ? "
                    "WHERE (source_id = ? OR target_id = ?) AND status = ?",
                    (RETRACTED, _now(), subject_id, subject_id, ACTIVE),
                )
            conn.execute("UPDATE claims SET status = ?, note = COALESCE(note,'') || ? "
                         "WHERE subject_id = ?",
                         (RETRACTED, f" | retracted: {reason}" if reason else " | retracted",
                          subject_id))
        return {"status": "ok", "retracted": subject_id, "kind": table[:-1], "reason": reason}

    def contradictions(self) -> list[dict[str, Any]]:
        """Single-valued relations that still hold more than one active object."""
        with self._lock, self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT source_id, relation, COUNT(DISTINCT target_id) AS n "
                "FROM edges WHERE status = ? GROUP BY source_id, relation HAVING n > 1",
                (ACTIVE,),
            )]
        out = []
        for row in rows:
            if row["relation"] not in UNIQUE_RELATIONS:
                continue
            node = self.get_node(row["source_id"]) or {"name": row["source_id"]}
            targets = [e["other_name"] for e in self.edges_of(row["source_id"],
                                                              relation=row["relation"])]
            out.append({"node": node["name"], "relation": row["relation"],
                        "targets": targets, "count": row["n"]})
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE status = ?",
                                 (ACTIVE,)).fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges WHERE status = ?",
                                 (ACTIVE,)).fetchone()[0]
            claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            retracted = conn.execute("SELECT COUNT(*) FROM claims WHERE status != ?",
                                     (ACTIVE,)).fetchone()[0]
            avg = conn.execute("SELECT AVG(confidence) FROM claims WHERE status = ?",
                               (ACTIVE,)).fetchone()[0]
            top = [dict(r) for r in conn.execute(
                "SELECT relation, COUNT(*) AS uses FROM edges WHERE status = ? "
                "GROUP BY relation ORDER BY uses DESC LIMIT 5", (ACTIVE,))]
        return {"nodes": nodes, "edges": edges, "claims": claims,
                "withdrawn_claims": retracted,
                "avg_confidence": round(avg or 0.0, 3),
                "top_relations": top,
                "contradictions": len(self.contradictions())}

    def health(self) -> dict[str, Any]:
        try:
            data = self.stats()
            return {"available": True, "db": self.db_path, **data}
        except Exception as exc:  # pragma: no cover - surfaced, never hidden
            return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------ pipeline entry point

    def run(self, action: str = "stats", **kwargs: Any) -> dict[str, Any]:
        """Entry point used by the manager registry / execution engine."""
        actions = {
            "add_node": self.add_node,
            "relate": self.relate,
            "neighbours": self.neighbours,
            "neighbors": self.neighbours,
            "path": self.path,
            "explain": self.explain,
            "provenance": lambda **kw: {"status": "ok", "claims": self.provenance(**kw)},
            "nodes": lambda **kw: {"status": "ok", "nodes": self.nodes(**kw)},
            "retract": self.retract,
            "contradictions": lambda: {"status": "ok",
                                       "contradictions": self.contradictions()},
            "stats": lambda: {"status": "ok", **self.stats()},
            "health": lambda: {"status": "ok", **self.health()},
        }
        handler = actions.get(str(action))
        if handler is None:
            return {"status": "invalid_input",
                    "error": f"unknown knowledge action '{action}'",
                    "supported": sorted(actions)}
        try:
            return handler(**kwargs)
        except TypeError as exc:
            return {"status": "invalid_input",
                    "error": f"bad arguments for '{action}': {exc}"}


_GRAPH: Optional[KnowledgeGraph] = None


def get_knowledge_graph(db_path: Optional[str] = None, kernel: Any = None) -> KnowledgeGraph:
    global _GRAPH
    if _GRAPH is None or db_path is not None:
        _GRAPH = KnowledgeGraph(db_path, kernel=kernel)
    return _GRAPH
