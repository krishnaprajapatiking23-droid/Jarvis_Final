"""Experience data models for BrainV2 learning."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class ExperienceType(Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    CORRECTION = 'correction'
    USER_FEEDBACK = 'user_feedback'
    PATTERN = 'pattern'
    STRATEGY = 'strategy'


@dataclass
class Experience:
    id: str
    type: ExperienceType
    context: str
    action: str
    outcome: str
    success: bool
    manager_used: str = ''
    execution_time: float = 0.0
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id, 'type': self.type.value, 'context': self.context,
            'action': self.action, 'outcome': self.outcome, 'success': self.success,
            'manager_used': self.manager_used, 'execution_time': self.execution_time,
            'tags': self.tags, 'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat(), 'metadata': self.metadata,
        }


class ExperienceStore:
    """Persistent storage for experiences."""

    def __init__(self, file_path: str):
        import json
        from pathlib import Path
        self.path = Path(file_path)
        self._experiences: List[Dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            import json
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self._experiences = json.load(f)
            except Exception:
                self._experiences = []

    def save(self):
        import json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self._experiences, f, indent=2, default=str)

    def add(self, exp: Dict):
        self._experiences.append(exp)
        self.save()

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        q = query.lower()
        return [e for e in reversed(self._experiences) if q in e.get('context', '').lower()][:limit]
