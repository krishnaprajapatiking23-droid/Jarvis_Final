"""S1 Dependency graph + plan visualization for tasks, tools, managers, steps.

Real graph: cycle rejection, topological execution waves, impact analysis,
critical path, ASCII/DOT rendering.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

NODE_KINDS = ("task", "tool", "manager", "step", "agent", "resource")


class CycleError(ValueError):
    """Raised when an edge would introduce a dependency cycle."""

    def __init__(self, path: Sequence[str]):
        self.path = list(path)
        super().__init__("dependency cycle: " + " -> ".join(self.path))


@dataclass
class Node:
    node_id: str
    kind: str
    label: str
    cost: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)


class DependencyGraph:
    """Directed acyclic graph. Edge a->b means "b depends on a"."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.nodes: Dict[str, Node] = {}
        self._out: Dict[str, Set[str]] = {}
        self._in: Dict[str, Set[str]] = {}

    # -------- construction --------
    def add_node(self, node_id: str, kind: str = "task", label: Optional[str] = None,
                 cost: float = 1.0, **meta: Any) -> Node:
        if kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind {kind!r}")
        if not node_id:
            raise ValueError("node_id required")
        with self._lock:
            node = self.nodes.get(node_id)
            if node is None:
                node = Node(node_id, kind, label or node_id, cost, dict(meta))
                self.nodes[node_id] = node
                self._out.setdefault(node_id, set())
                self._in.setdefault(node_id, set())
            else:
                node.kind = kind
                node.label = label or node.label
                node.cost = cost
                node.meta.update(meta)
            return node

    def add_dependency(self, dependency: str, dependent: str) -> Tuple[str, str]:
        """`dependent` requires `dependency` to finish first."""
        with self._lock:
            for n in (dependency, dependent):
                if n not in self.nodes:
                    self.add_node(n)
            if dependency == dependent:
                raise CycleError([dependency, dependent])
            # would adding create a cycle? only if dependent already reaches dependency
            path = self._find_path(dependent, dependency)
            if path:
                raise CycleError(path + [dependent])
            self._out[dependency].add(dependent)
            self._in[dependent].add(dependency)
            return dependency, dependent

    def remove_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id not in self.nodes:
                return False
            for p in list(self._in[node_id]):
                self._out[p].discard(node_id)
            for c in list(self._out[node_id]):
                self._in[c].discard(node_id)
            del self._in[node_id], self._out[node_id], self.nodes[node_id]
            return True

    # -------- traversal --------
    def _find_path(self, src: str, dst: str) -> Optional[List[str]]:
        if src not in self.nodes or dst not in self.nodes:
            return None
        stack = [(src, [src])]
        seen: Set[str] = set()
        while stack:
            cur, path = stack.pop()
            if cur == dst:
                return path
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in self._out.get(cur, ()):
                stack.append((nxt, path + [nxt]))
        return None

    def dependencies_of(self, node_id: str) -> List[str]:
        return sorted(self._in.get(node_id, set()))

    def dependents_of(self, node_id: str) -> List[str]:
        return sorted(self._out.get(node_id, set()))

    def ancestors(self, node_id: str) -> Set[str]:
        out: Set[str] = set()
        stack = list(self._in.get(node_id, set()))
        while stack:
            n = stack.pop()
            if n in out:
                continue
            out.add(n)
            stack.extend(self._in.get(n, set()))
        return out

    def descendants(self, node_id: str) -> Set[str]:
        out: Set[str] = set()
        stack = list(self._out.get(node_id, set()))
        while stack:
            n = stack.pop()
            if n in out:
                continue
            out.add(n)
            stack.extend(self._out.get(n, set()))
        return out

    def impact_of(self, node_id: str) -> Dict[str, Any]:
        """Change impact analysis: what breaks if this node changes/fails."""
        desc = self.descendants(node_id)
        return {
            "node": node_id,
            "direct": self.dependents_of(node_id),
            "transitive": sorted(desc),
            "blast_radius": len(desc),
            "kinds": sorted({self.nodes[d].kind for d in desc if d in self.nodes}),
        }

    def topological_order(self) -> List[str]:
        with self._lock:
            indeg = {n: len(self._in[n]) for n in self.nodes}
            ready = sorted([n for n, d in indeg.items() if d == 0])
            order: List[str] = []
            while ready:
                n = ready.pop(0)
                order.append(n)
                for c in sorted(self._out[n]):
                    indeg[c] -= 1
                    if indeg[c] == 0:
                        ready.append(c)
                ready.sort()
            if len(order) != len(self.nodes):
                remaining = [n for n in self.nodes if n not in order]
                raise CycleError(remaining)
            return order

    def execution_waves(self) -> List[List[str]]:
        """Groups of nodes that can run in parallel, in dependency order."""
        with self._lock:
            indeg = {n: len(self._in[n]) for n in self.nodes}
            waves: List[List[str]] = []
            done: Set[str] = set()
            while len(done) < len(self.nodes):
                wave = sorted([n for n, d in indeg.items() if d == 0 and n not in done])
                if not wave:
                    raise CycleError([n for n in self.nodes if n not in done])
                waves.append(wave)
                for n in wave:
                    done.add(n)
                    for c in self._out[n]:
                        indeg[c] -= 1
                    indeg[n] = -1
            return waves

    def critical_path(self) -> Dict[str, Any]:
        order = self.topological_order()
        best: Dict[str, float] = {}
        prev: Dict[str, Optional[str]] = {}
        for n in order:
            options = [(best[p] , p) for p in self._in[n] if p in best]
            base, parent = max(options) if options else (0.0, None)
            best[n] = base + self.nodes[n].cost
            prev[n] = parent
        if not best:
            return {"length": 0.0, "path": []}
        end = max(best, key=lambda k: best[k])
        path = [end]
        while prev.get(path[-1]):
            path.append(prev[path[-1]])  # type: ignore[arg-type]
        return {"length": round(best[end], 3), "path": list(reversed(path))}

    # -------- visualization (S1 Plan Visualization) --------
    def render_ascii(self, title: str = "PLAN") -> str:
        waves = self.execution_waves()
        lines = [f"{title} ({len(self.nodes)} nodes, {sum(len(v) for v in self._out.values())} edges)"]
        for i, wave in enumerate(waves, 1):
            lines.append(f"  wave {i}:")
            for n in wave:
                node = self.nodes[n]
                deps = self.dependencies_of(n)
                suffix = f"  <- {', '.join(deps)}" if deps else ""
                lines.append(f"    [{node.kind}] {node.label}{suffix}")
        cp = self.critical_path()
        lines.append(f"  critical path ({cp['length']}): {' -> '.join(cp['path'])}")
        return "\n".join(lines)

    def to_dot(self) -> str:
        rows = ["digraph plan {", '  rankdir=LR;', '  node [shape=box, style=rounded];']
        for n, node in self.nodes.items():
            rows.append(f'  "{n}" [label="{node.label}\\n({node.kind})"];')
        for a, outs in self._out.items():
            for b in outs:
                rows.append(f'  "{a}" -> "{b}";')
        rows.append("}")
        return "\n".join(rows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {"id": n.node_id, "kind": n.kind, "label": n.label, "cost": n.cost, "meta": n.meta}
                for n in self.nodes.values()
            ],
            "edges": [[a, b] for a, outs in self._out.items() for b in sorted(outs)],
        }

    @classmethod
    def from_plan(cls, steps: Iterable[Dict[str, Any]]) -> "DependencyGraph":
        """Build from a planner output: [{id, label, kind, cost, depends_on:[..]}]."""
        g = cls()
        steps = list(steps)
        for s in steps:
            g.add_node(str(s["id"]), s.get("kind", "step"), s.get("label"), float(s.get("cost", 1.0)))
        for s in steps:
            for dep in s.get("depends_on", ()) or ():
                g.add_dependency(str(dep), str(s["id"]))
        return g
