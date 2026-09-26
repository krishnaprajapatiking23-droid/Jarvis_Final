"""Research manager (Section 14).

Evidence extraction, conflict detection, contradiction resolution, source
quality scoring, a real stopping condition and a persistent cache.

The manager works on *fetched documents*; the fetcher is injected so the same
logic runs against the project's existing `browser_ai.search`/`website_reader`
helpers, the web module, or a test double. Without a fetcher every research
call returns `unavailable` rather than inventing sources.

State: SQLite (`research.db`) - tables `research_claims`, `research_cache`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Domain-class reliability priors. Refined per source by corroboration.
DOMAIN_QUALITY = {
    "peer_reviewed": 0.95, "standards_body": 0.93, "official_docs": 0.9,
    "government": 0.88, "reference": 0.75, "news": 0.65, "vendor": 0.6,
    "forum": 0.45, "blog": 0.4, "social": 0.25, "unknown": 0.35,
}

_DOMAIN_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"(arxiv\.org|nature\.com|sciencedirect|ieee\.org|acm\.org|pubmed)", "peer_reviewed"),
    (r"(w3\.org|ietf\.org|iso\.org|unicode\.org)", "standards_body"),
    (r"(docs\.|developer\.|\.readthedocs\.io|python\.org)", "official_docs"),
    (r"(\.gov|\.gov\.[a-z]{2}|who\.int|europa\.eu)", "government"),
    (r"(wikipedia\.org|britannica\.com)", "reference"),
    (r"(reuters\.com|apnews\.com|bbc\.co|nytimes\.com|thehindu\.com)", "news"),
    (r"(stackoverflow\.com|stackexchange\.com|reddit\.com/r/|quora\.com)", "forum"),
    (r"(medium\.com|substack\.com|blogspot|wordpress\.com|dev\.to)", "blog"),
    (r"(twitter\.com|x\.com|facebook\.com|instagram\.com|tiktok\.com)", "social"),
)

_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_NEGATION = re.compile(r"\b(not|never|no longer|isn'?t|aren'?t|doesn'?t|cannot|can'?t)\b", re.I)
_STOP = frozenset("""a an the is are was were be been being of to in on for with and or as at by
this that these those it its from about into than then there their has have had do does did will
would can could should may might must very more most some any which who whom what when where how
""".split())

DEFAULT_MIN_SOURCES = 3
DEFAULT_CONFIDENCE_TARGET = 0.8
DEFAULT_CACHE_TTL_HOURS = 24.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _outcome(status: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": status == "ok", "status": status}
    out.update(extra)
    return out


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9.%$]+", (text or "").lower())
            if len(t) > 2 and t not in _STOP]


def classify_source(url: str) -> str:
    lowered = (url or "").lower()
    for pattern, label in _DOMAIN_PATTERNS:
        if re.search(pattern, lowered):
            return label
    return "unknown"


@dataclass
class Evidence:
    """One extracted claim with the sentence that supports it."""
    id: str
    question: str
    source: str
    source_class: str
    claim: str
    evidence: str
    quality: float
    confidence: float
    numbers: List[str] = field(default_factory=list)
    negated: bool = False
    timestamp: str = field(default_factory=_utc)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "question": self.question, "source": self.source,
                "source_class": self.source_class, "claim": self.claim,
                "evidence": self.evidence, "quality": round(self.quality, 4),
                "confidence": round(self.confidence, 4), "numbers": list(self.numbers),
                "negated": self.negated, "timestamp": self.timestamp}


class ResearchManager:
    """Capability: "research". Registered on the kernel manager registry.

    fetcher(query) -> iterable of {"url": str, "text": str, "published"?: str}
    """

    capability = "research"

    def __init__(self, db_path: Optional[str] = None,
                 fetcher: Optional[Callable[[str], Iterable[Dict[str, Any]]]] = None,
                 kernel: Any = None, cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS):
        self.kernel = kernel
        self.fetcher = fetcher
        self.cache_ttl_hours = float(cache_ttl_hours)
        path = db_path or os.path.join(_DEF_DIR, "research.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_claims(
                    id TEXT PRIMARY KEY, question TEXT, source TEXT, source_class TEXT,
                    claim TEXT, evidence TEXT, quality REAL, confidence REAL,
                    numbers TEXT, negated INTEGER, timestamp TEXT);
                CREATE TABLE IF NOT EXISTS research_cache(
                    key TEXT PRIMARY KEY, question TEXT, payload TEXT, created_at TEXT,
                    hits INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS idx_claims_question ON research_claims(question);
                """
            )
            self._conn.commit()

    # ---------------- evidence extraction ----------------
    def extract_evidence(self, question: str, document: Dict[str, Any]) -> List[Evidence]:
        """Pull the sentences that actually bear on the question, not the whole page."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        url = str(document.get("url") or "")
        text = str(document.get("text") or "")
        if not text.strip():
            return []
        terms = set(_tokens(question))
        source_class = classify_source(url)
        base_quality = DOMAIN_QUALITY.get(source_class, DOMAIN_QUALITY["unknown"])
        found: List[Evidence] = []
        for sentence in _SENTENCE.split(text.strip()):
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            stoks = set(_tokens(sentence))
            overlap = len(terms & stoks)
            if overlap < 2:
                continue
            relevance = overlap / max(1, len(terms))
            numbers = _NUMBER.findall(sentence)
            specificity = 0.1 if numbers else 0.0
            confidence = round(min(0.99, 0.35 + 0.45 * relevance + specificity +
                                   0.15 * base_quality), 4)
            found.append(Evidence(
                id="EV-" + uuid.uuid4().hex[:10], question=question.strip(), source=url,
                source_class=source_class, claim=sentence, evidence=sentence,
                quality=base_quality, confidence=confidence, numbers=numbers,
                negated=bool(_NEGATION.search(sentence)),
            ))
        found.sort(key=lambda e: -e.confidence)
        for item in found:
            self._store_claim(item)
        return found

    def _store_claim(self, ev: Evidence) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO research_claims(id, question, source, source_class,"
                " claim, evidence, quality, confidence, numbers, negated, timestamp)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ev.id, ev.question, ev.source, ev.source_class, ev.claim, ev.evidence,
                 ev.quality, ev.confidence, json.dumps(ev.numbers), int(ev.negated),
                 ev.timestamp))
            self._conn.commit()

    def claims(self, question: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM research_claims"
        params: List[Any] = []
        if question:
            sql += " WHERE question=?"
            params.append(question.strip())
        sql += " ORDER BY confidence DESC"
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ---------------- source quality ----------------
    def score_source(self, url: str, corroborations: int = 0,
                     contradictions: int = 0) -> Dict[str, Any]:
        """Prior by domain class, adjusted by how often the source agrees with others."""
        source_class = classify_source(url)
        prior = DOMAIN_QUALITY.get(source_class, DOMAIN_QUALITY["unknown"])
        support = 0.06 * math.log1p(max(0, corroborations))
        penalty = 0.12 * math.log1p(max(0, contradictions))
        score = max(0.05, min(0.99, prior + support - penalty))
        return {"source": url, "class": source_class, "prior": prior,
                "corroborations": corroborations, "contradictions": contradictions,
                "score": round(score, 4),
                "reason": f"{source_class} prior {prior} +{support:.3f} support -{penalty:.3f} conflict"}

    # ---------------- conflict detection / resolution ----------------
    def detect_conflicts(self, evidence: Sequence[Evidence]) -> List[Dict[str, Any]]:
        """Real disagreement detection: incompatible numbers, or negation flips."""
        conflicts: List[Dict[str, Any]] = []
        items = list(evidence)
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.source == b.source:
                    continue
                shared = set(_tokens(a.claim)) & set(_tokens(b.claim))
                if len(shared) < 2:
                    continue
                kind = None
                if a.numbers and b.numbers:
                    na = {n.replace(",", "") for n in a.numbers}
                    nb = {n.replace(",", "") for n in b.numbers}
                    if na != nb and not (na & nb):
                        kind = "numeric_disagreement"
                if kind is None and a.negated != b.negated:
                    kind = "polarity_disagreement"
                if kind is None:
                    continue
                conflicts.append({
                    "kind": kind, "topic": sorted(shared)[:6],
                    "a": a.to_dict(), "b": b.to_dict(),
                })
        return conflicts

    def resolve_conflict(self, conflict: Dict[str, Any],
                         corroboration: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Resolve by evidence quality, never by 'first result wins'."""
        corroboration = corroboration or {}
        scored = []
        for side in ("a", "b"):
            item = conflict[side]
            score = self.score_source(item["source"],
                                      corroborations=corroboration.get(item["source"], 0))
            weight = 0.6 * score["score"] + 0.4 * float(item["confidence"])
            scored.append((weight, side, item, score))
        scored.sort(key=lambda s: -s[0])
        best, loser = scored[0], scored[1]
        margin = best[0] - loser[0]
        resolved = margin >= 0.05
        return {
            "resolved": resolved,
            "winner": best[2] if resolved else None,
            "winner_weight": round(best[0], 4),
            "loser": loser[2],
            "loser_weight": round(loser[0], 4),
            "margin": round(margin, 4),
            "kind": conflict["kind"],
            "conflict_preserved": True,
            "reason": (f"{best[3]['class']} source outweighs {loser[3]['class']} source "
                       f"({best[0]:.3f} vs {loser[0]:.3f})") if resolved else
                      "evidence quality too close to call - escalate to the user",
        }

    # ---------------- stopping condition ----------------
    def should_stop(self, evidence: Sequence[Evidence], conflicts: Sequence[Dict[str, Any]],
                    min_sources: int = DEFAULT_MIN_SOURCES,
                    confidence_target: float = DEFAULT_CONFIDENCE_TARGET,
                    max_rounds: int = 4, round_index: int = 0) -> Dict[str, Any]:
        sources = {e.source for e in evidence}
        best = max((e.confidence for e in evidence), default=0.0)
        unresolved = [c for c in conflicts]
        if round_index + 1 >= max_rounds:
            return {"stop": True, "reason": f"round budget exhausted ({max_rounds})",
                    "sources": len(sources), "best_confidence": round(best, 4)}
        if len(sources) >= min_sources and best >= confidence_target and not unresolved:
            return {"stop": True,
                    "reason": (f"{len(sources)} independent sources agree with confidence "
                               f"{best:.2f} >= {confidence_target}"),
                    "sources": len(sources), "best_confidence": round(best, 4)}
        missing = []
        if len(sources) < min_sources:
            missing.append(f"need {min_sources - len(sources)} more source(s)")
        if best < confidence_target:
            missing.append(f"confidence {best:.2f} below target {confidence_target}")
        if unresolved:
            missing.append(f"{len(unresolved)} unresolved conflict(s)")
        return {"stop": False, "reason": "; ".join(missing), "sources": len(sources),
                "best_confidence": round(best, 4)}

    # ---------------- cache ----------------
    def _cache_key(self, question: str) -> str:
        return hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()[:24]

    def cache_get(self, question: str) -> Optional[Dict[str, Any]]:
        key = self._cache_key(question)
        with self._lock:
            row = self._conn.execute("SELECT * FROM research_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        created = datetime.fromisoformat(row["created_at"])
        if datetime.now(timezone.utc) - created > timedelta(hours=self.cache_ttl_hours):
            with self._lock:
                self._conn.execute("DELETE FROM research_cache WHERE key=?", (key,))
                self._conn.commit()
            return None
        with self._lock:
            self._conn.execute("UPDATE research_cache SET hits=hits+1 WHERE key=?", (key,))
            self._conn.commit()
        payload = json.loads(row["payload"])
        payload["cached"] = True
        payload["cache_age_seconds"] = int(
            (datetime.now(timezone.utc) - created).total_seconds())
        return payload

    def cache_put(self, question: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO research_cache(key, question, payload, created_at, hits)"
                " VALUES(?,?,?,?,COALESCE((SELECT hits FROM research_cache WHERE key=?),0))",
                (self._cache_key(question), question.strip(),
                 json.dumps(payload, default=str), _utc(), self._cache_key(question)))
            self._conn.commit()

    def cache_stats(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS entries, COALESCE(SUM(hits),0) AS hits FROM research_cache"
            ).fetchone()
        return {"entries": row["entries"], "hits": row["hits"],
                "ttl_hours": self.cache_ttl_hours}

    # ---------------- top-level research loop ----------------
    def research(self, question: str, min_sources: int = DEFAULT_MIN_SOURCES,
                 confidence_target: float = DEFAULT_CONFIDENCE_TARGET,
                 max_rounds: int = 4, use_cache: bool = True) -> Dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            return _outcome("invalid_input", reason="question must be a non-empty string")
        if use_cache:
            cached = self.cache_get(question)
            if cached:
                return cached
        if self.fetcher is None:
            return _outcome("unavailable",
                            reason="no research fetcher configured (no web/browser backend)")
        evidence: List[Evidence] = []
        rounds: List[Dict[str, Any]] = []
        stop = {"stop": False, "reason": "not started"}
        for round_index in range(max_rounds):
            try:
                docs = list(self.fetcher(question))
            except Exception as exc:
                return _outcome("failure", error=f"{type(exc).__name__}: {exc}",
                                rounds=rounds, evidence=[e.to_dict() for e in evidence])
            new_items: List[Evidence] = []
            for doc in docs:
                if any(e.source == str(doc.get("url")) for e in evidence):
                    continue
                new_items.extend(self.extract_evidence(question, doc))
            evidence.extend(new_items)
            conflicts = self.detect_conflicts(evidence)
            resolutions = [self.resolve_conflict(c) for c in conflicts]
            unresolved = [r for r in resolutions if not r["resolved"]]
            stop = self.should_stop(evidence, unresolved, min_sources, confidence_target,
                                    max_rounds, round_index)
            rounds.append({"round": round_index + 1, "documents": len(docs),
                           "new_evidence": len(new_items), "conflicts": len(conflicts),
                           "unresolved": len(unresolved), "stop": stop})
            if stop["stop"]:
                break
            if not new_items and round_index:
                stop = {"stop": True, "reason": "no new evidence available from the fetcher",
                        "sources": stop["sources"], "best_confidence": stop["best_confidence"]}
                break
        conflicts = self.detect_conflicts(evidence)
        resolutions = [self.resolve_conflict(c) for c in conflicts]
        answer = max(evidence, key=lambda e: (e.confidence, e.quality)) if evidence else None
        payload = _outcome(
            "ok" if evidence else "not_found",
            question=question.strip(),
            answer=answer.to_dict() if answer else None,
            evidence=[e.to_dict() for e in evidence],
            sources=sorted({e.source for e in evidence}),
            source_scores=[self.score_source(s) for s in sorted({e.source for e in evidence})],
            conflicts=conflicts, resolutions=resolutions, rounds=rounds,
            stopped_because=stop.get("reason"), cached=False,
        )
        analytics = getattr(self.kernel, "analytics", None)
        if analytics is not None:
            try:
                analytics.record("tool", "research.research", bool(evidence))
            except Exception:
                pass
        if evidence:
            self.cache_put(question, payload)
        return payload

    def health(self) -> Dict[str, Any]:
        return {"available": self.fetcher is not None,
                "fetcher": getattr(self.fetcher, "__name__", type(self.fetcher).__name__),
                "cache": self.cache_stats()}

    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        handlers = {"research": self.research, "score_source": self.score_source,
                    "cache_stats": self.cache_stats, "health": self.health}
        handler = handlers.get(action)
        if handler is None:
            return _outcome("invalid_input", reason=f"unknown research action {action!r}",
                            supported=sorted(handlers))
        try:
            return handler(**kwargs)
        except TypeError as exc:
            return _outcome("invalid_input", reason=str(exc))


__all__ = ["ResearchManager", "Evidence", "classify_source", "DOMAIN_QUALITY"]
