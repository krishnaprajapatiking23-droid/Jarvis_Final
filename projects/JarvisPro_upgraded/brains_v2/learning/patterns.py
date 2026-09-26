"""Pattern detection for BrainV2 learning."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class PatternType(Enum):
    COMMAND_SEQUENCE = 'command_sequence'
    TIME_BASED = 'time_based'
    CONTEXT_TRIGGER = 'context_trigger'
    MANAGER_USAGE = 'manager_usage'
    FAILURE = 'failure'
    SUCCESS = 'success'


@dataclass
class Pattern:
    id: str
    type: PatternType
    name: str
    description: str
    occurrence_count: int = 1
    success_count: int = 0
    avg_execution_time: float = 0.0
    tags: List[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.occurrence_count == 0:
            return 0.0
        return self.success_count / self.occurrence_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id, 'type': self.type.value, 'name': self.name,
            'description': self.description,
            'occurrence_count': self.occurrence_count,
            'success_rate': self.success_rate,
            'confidence': self.confidence,
            'tags': self.tags,
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat(),
        }


class PatternDetector:
    """Detects patterns from command history and execution data."""

    def __init__(self):
        self._patterns: List[Pattern] = []

    def detect(self, experiences: List[Dict]) -> List[Pattern]:
        """Analyze experiences and extract patterns."""
        detected = []
        # Group by context keywords
        from collections import defaultdict
        context_groups: Dict[str, List[Dict]] = defaultdict(list)
        for exp in experiences[-100:]:
            words = [w for w in exp.get('context', '').split() if len(w) > 4]
            for word in words[:3]:
                context_groups[word].append(exp)
        for keyword, exps in context_groups.items():
            if len(exps) >= 3:
                success_rate = sum(1 for e in exps if e.get('success')) / len(exps)
                p = Pattern(
                    id=f'pattern_{keyword[:20]}',
                    type=PatternType.CONTEXT_TRIGGER,
                    name=f'Context: {keyword}',
                    description=f'Seen "{keyword}" in {len(exps)} experiences',
                    occurrence_count=len(exps),
                    success_count=sum(1 for e in exps if e.get('success')),
                    confidence=min(1.0, len(exps) / 20),
                    last_seen=datetime.now(),
                )
                detected.append(p)
        return detected

    def get_frequent_patterns(self, min_occurrences: int = 3) -> List[Pattern]:
        return [p for p in self._patterns if p.occurrence_count >= min_occurrences]
