"""S1/S16 Decision explanation, fallback manager selection, manager health checks,
and S2 context conflict resolution + context-aware decisions.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# Manager registry + health (S16)
# ----------------------------------------------------------------------------
@dataclass
class ManagerHealth:
    name: str
    available: bool = True
    dependencies: List[str] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return 1.0 if total == 0 else round(self.successes / total, 4)

    @property
    def status(self) -> str:
        if not self.available:
            return "failed"
        if self.consecutive_failures >= 3:
            return "failed"
        if self.consecutive_failures > 0 or self.success_rate < 0.6:
            return "degraded"
        return "healthy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "available": self.available, "healthy": self.status == "healthy",
            "degraded": self.status == "degraded", "failed": self.status == "failed",
            "status": self.status, "dependencies": list(self.dependencies),
            "last_success": self.last_success, "last_failure": self.last_failure,
            "last_error": self.last_error, "success_rate": self.success_rate,
            "successes": self.successes, "failures": self.failures,
        }


class ManagerRegistry:
    """Capability registry with real health probes and fallback selection."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._managers: Dict[str, Any] = {}
        self._order: Dict[str, int] = {}
        self._caps: Dict[str, List[str]] = {}
        self._health: Dict[str, ManagerHealth] = {}
        self._probes: Dict[str, Callable[[], bool]] = {}

    def register(self, name: str, instance: Any, capabilities: Iterable[str],
                 dependencies: Iterable[str] = (), probe: Optional[Callable[[], bool]] = None) -> None:
        with self._lock:
            if name not in self._order:
                self._order[name] = len(self._order)
            self._managers[name] = instance
            self._caps[name] = sorted(set(capabilities))
            self._health[name] = ManagerHealth(name, True, sorted(set(dependencies)))
            if probe:
                self._probes[name] = probe

    def get(self, name: str) -> Any:
        return self._managers.get(name)

    def capabilities(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._caps.items()}

    def managers_for(self, capability: str) -> List[str]:
        return [n for n, caps in self._caps.items() if capability in caps]

    def record(self, name: str, ok: bool, error: Optional[str] = None) -> ManagerHealth:
        with self._lock:
            h = self._health.setdefault(name, ManagerHealth(name))
            if ok:
                h.successes += 1
                h.consecutive_failures = 0
                h.last_success = _utc()
            else:
                h.failures += 1
                h.consecutive_failures += 1
                h.last_failure = _utc()
                h.last_error = error
            return h

    def health_check(self, name: Optional[str] = None) -> Dict[str, Any]:
        names = [name] if name else list(self._health)
        out: Dict[str, Any] = {}
        for n in names:
            h = self._health.get(n)
            if h is None:
                out[n] = {"name": n, "available": False, "status": "failed", "error": "not registered"}
                continue
            probe = self._probes.get(n)
            if probe:
                try:
                    h.available = bool(probe())
                except Exception as exc:
                    h.available = False
                    h.last_error = f"probe failed: {exc}"
            missing = [d for d in h.dependencies if d not in self._managers]
            d = h.to_dict()
            d["missing_dependencies"] = missing
            if missing:
                d["status"] = "degraded" if d["status"] == "healthy" else d["status"]
            out[n] = d
        return out

    # ---------------- fallback selection (S1) ----------------
    def select(self, capability: str, exclude: Iterable[str] = ()) -> Dict[str, Any]:
        exclude = set(exclude)
        candidates = []
        for n in self.managers_for(capability):
            if n in exclude:
                continue
            h = self._health.get(n) or ManagerHealth(n)
            if h.status == "failed":
                continue
            score = h.success_rate - (0.25 if h.status == "degraded" else 0.0)
            candidates.append((score, self._order.get(n, 999), n, h))
        if not candidates:
            return {"manager": None, "reason": f"no healthy manager provides {capability}",
                    "considered": self.managers_for(capability)}
        # highest score first; ties resolved by registration order (primary before backup)
        candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
        score, _order, name, h = candidates[0]
        return {
            "manager": name, "score": round(score, 4), "status": h.status,
            "alternatives": [c[2] for c in candidates[1:]],
            "reason": f"{name} provides {capability} with success rate {h.success_rate} ({h.status})",
        }

    def execute_with_fallback(self, capability: str, method: str, *args: Any,
                              max_attempts: int = 3, **kwargs: Any) -> Dict[str, Any]:
        """Try the best manager; on failure fall back to the next healthy one."""
        tried: List[str] = []
        errors: List[Dict[str, str]] = []
        for _ in range(max_attempts):
            pick = self.select(capability, exclude=tried)
            name = pick.get("manager")
            if not name:
                break
            tried.append(name)
            mgr = self._managers.get(name)
            fn = getattr(mgr, method, None)
            if not callable(fn):
                errors.append({"manager": name, "error": f"missing method {method}"})
                self.record(name, False, f"missing method {method}")
                continue
            try:
                result = fn(*args, **kwargs)
                self.record(name, True)
                return {"ok": True, "manager": name, "result": result, "attempts": tried,
                        "fallbacks_used": len(tried) - 1, "errors": errors}
            except Exception as exc:
                self.record(name, False, str(exc))
                errors.append({"manager": name, "error": f"{type(exc).__name__}: {exc}"})
        return {"ok": False, "manager": None, "attempts": tried, "errors": errors,
                "reason": f"all candidates for {capability} failed"}


# ----------------------------------------------------------------------------
# Decision engine with explanation (S1)
# ----------------------------------------------------------------------------
@dataclass
class Explanation:
    choice: str
    confidence: float
    factors: List[Dict[str, Any]]
    alternatives: List[Dict[str, Any]]
    context_used: List[str]
    created_at: str = field(default_factory=_utc)

    def to_text(self) -> str:
        lines = [f"Chose '{self.choice}' (confidence {self.confidence:.2%}).", "Because:"]
        for f in sorted(self.factors, key=lambda x: -abs(x["contribution"])):
            sign = "+" if f["contribution"] >= 0 else "-"
            lines.append(f"  {sign} {f['name']}: {f['detail']} ({f['contribution']:+.3f})")
        if self.alternatives:
            alt = ", ".join(f"{a['option']} {a['score']:.3f}" for a in self.alternatives)
            lines.append(f"Runner-up options: {alt}")
        if self.context_used:
            lines.append("Context used: " + ", ".join(self.context_used))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "choice": self.choice, "confidence": self.confidence, "factors": self.factors,
            "alternatives": self.alternatives, "context_used": self.context_used,
            "created_at": self.created_at, "text": self.to_text(),
        }


class DecisionEngine:
    """Weighted, explainable scoring. Every decision is recorded so Jarvis can
    answer "why did you do that?" later."""

    def __init__(self, history_limit: int = 200):
        self.history: List[Explanation] = []
        self.history_limit = history_limit
        self._lock = threading.RLock()

    def decide(self, options: Dict[str, Dict[str, float]], weights: Optional[Dict[str, float]] = None,
               context_used: Iterable[str] = (), details: Optional[Dict[str, Dict[str, str]]] = None) -> Explanation:
        """options: {option: {factor: value 0..1}}; weights: {factor: weight}."""
        if not options:
            raise ValueError("no options to decide between")
        factors = sorted({f for vals in options.values() for f in vals})
        weights = weights or {f: 1.0 for f in factors}
        scores: Dict[str, float] = {}
        contrib: Dict[str, List[Dict[str, Any]]] = {}
        for opt, vals in options.items():
            total = 0.0
            rows = []
            for f in factors:
                w = float(weights.get(f, 0.0))
                v = float(vals.get(f, 0.0))
                c = w * v
                total += c
                rows.append({
                    "name": f, "value": v, "weight": w, "contribution": round(c, 4),
                    "detail": (details or {}).get(opt, {}).get(f, f"{f}={v:.2f} x weight {w:.2f}"),
                })
            scores[opt] = total
            contrib[opt] = rows
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        best, best_score = ranked[0]
        exps = [math.exp(s) for _, s in ranked]
        confidence = round(exps[0] / sum(exps), 4)
        exp = Explanation(
            choice=best,
            confidence=confidence,
            factors=contrib[best],
            alternatives=[{"option": o, "score": round(s, 4)} for o, s in ranked[1:]],
            context_used=list(context_used),
        )
        with self._lock:
            self.history.append(exp)
            del self.history[:-self.history_limit]
        return exp

    def explain_last(self) -> Optional[str]:
        return self.history[-1].to_text() if self.history else None

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.history[-limit:]][::-1]


# ----------------------------------------------------------------------------
# Context engine: conflict resolution + context-aware decisions (S2)
# ----------------------------------------------------------------------------
SOURCE_PRIORITY = {
    "user_correction": 5.0,
    "explicit_user": 4.5,
    "profile": 3.5,
    "task": 3.0,
    "memory": 2.5,
    "conversation": 2.0,
    "environment": 1.5,
    "inference": 1.0,
}


@dataclass
class ContextItem:
    key: str
    value: Any
    source: str
    confidence: float = 0.6
    at: float = field(default_factory=time.time)
    ttl: Optional[float] = None
    note: str = ""

    @property
    def expired(self) -> bool:
        return self.ttl is not None and (time.time() - self.at) > self.ttl

    def weight(self) -> float:
        prio = SOURCE_PRIORITY.get(self.source, 1.0)
        age_h = (time.time() - self.at) / 3600.0
        recency = 1.0 / (1.0 + age_h)  # decays with age
        return round(prio * self.confidence * (0.5 + 0.5 * recency), 6)

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source,
                "confidence": self.confidence, "age_s": round(time.time() - self.at, 2),
                "weight": self.weight(), "note": self.note}


class ContextEngine:
    def __init__(self) -> None:
        self._items: List[ContextItem] = []
        self._lock = threading.RLock()

    def add(self, key: str, value: Any, source: str, confidence: float = 0.6,
            ttl: Optional[float] = None, note: str = "") -> ContextItem:
        item = ContextItem(key, value, source, confidence, ttl=ttl, note=note)
        with self._lock:
            self._items.append(item)
        return item

    def expire(self) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if not i.expired]
            return before - len(self._items)

    def items(self, key: Optional[str] = None) -> List[ContextItem]:
        self.expire()
        with self._lock:
            return [i for i in self._items if key is None or i.key == key]

    def conflicts(self, key: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        keys = {i.key for i in self.items(key)}
        for k in sorted(keys):
            vals = self.items(k)
            distinct = {str(i.value) for i in vals}
            if len(distinct) > 1:
                out.append({"key": k, "values": [i.to_dict() for i in vals]})
        return out

    def resolve(self, key: str) -> Dict[str, Any]:
        """Conflict resolution: user correction > source priority > confidence > recency.
        The disagreement is preserved, never silently dropped."""
        vals = self.items(key)
        if not vals:
            return {"key": key, "value": None, "resolved": False, "reason": "no context for key"}
        corrections = [i for i in vals if i.source == "user_correction"]
        pool = corrections or vals
        best = max(pool, key=lambda i: (i.weight(), i.at))
        losers = [i.to_dict() for i in vals if i is not best]
        distinct = {str(i.value) for i in vals}
        reason = (
            "explicit user correction overrides other sources" if corrections else
            f"source '{best.source}' has highest priority-confidence-recency weight {best.weight()}"
        )
        return {
            "key": key, "value": best.value, "resolved": True, "source": best.source,
            "confidence": best.confidence, "weight": best.weight(),
            "conflict": len(distinct) > 1, "reason": reason, "overridden": losers,
        }

    def snapshot(self, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        keys = list(keys) if keys else sorted({i.key for i in self.items()})
        return {k: self.resolve(k) for k in keys}

    def assemble(self, budget: int = 8) -> Dict[str, Any]:
        """Context assembly + ranking + compression under a size budget."""
        snap = self.snapshot()
        ranked = sorted(snap.values(), key=lambda r: -(r.get("weight") or 0))
        kept = ranked[:budget]
        dropped = ranked[budget:]
        return {
            "context": {r["key"]: r["value"] for r in kept},
            "ranked": kept,
            "dropped": [r["key"] for r in dropped],
            "conflicts": [r["key"] for r in ranked if r.get("conflict")],
            "compressed": "; ".join(f"{r['key']}={r['value']}" for r in kept),
        }

    def decide_with_context(self, engine: DecisionEngine, options: Dict[str, Dict[str, float]],
                            weights: Optional[Dict[str, float]] = None) -> Explanation:
        asm = self.assemble()
        return engine.decide(options, weights, context_used=list(asm["context"].keys()))
