"""BrainV2 Learning Engine — Core learning and adaptation logic."""

import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class LearningEngine:
    """Learns from experience to improve future performance."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = str(Path('data/brains_v2/learning').expanduser())
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.experiences_file = self.data_dir / 'experiences.json'
        self.patterns_file = self.data_dir / 'patterns.json'
        self.strategies_file = self.data_dir / 'strategies.json'
        self._experiences: List[Dict] = []
        self._patterns: List[Dict] = []
        self._strategies: Dict[str, Any] = {}
        self._load()

    def _load(self):
        for fname, dest in [
            (self.experiences_file, '_experiences'),
            (self.patterns_file, '_patterns'),
            (self.strategies_file, '_strategies'),
        ]:
            if fname.exists():
                try:
                    with open(fname, 'r', encoding='utf-8') as f:
                        setattr(self, dest, json.load(f))
                except Exception as e:
                    logger.error(f'Failed to load {fname}: {e}')

    def _save(self, data: Any, filename: Path):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f'Failed to save {filename}: {e}')

    def record_experience(
        self, context: str, action: str, outcome: str, success: bool,
        manager_used: str = '', execution_time: float = 0.0,
        tags: Optional[List[str]] = None, metadata: Optional[Dict] = None,
    ) -> str:
        """Record an experience for learning."""
        exp_id = str(uuid.uuid4())
        experience = {
            'id': exp_id,
            'context': context,
            'action': action,
            'outcome': outcome,
            'success': success,
            'manager_used': manager_used,
            'execution_time': execution_time,
            'tags': tags or [],
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat(),
            'confidence': 1.0 if success else 0.5,
        }
        self._experiences.append(experience)
        # Keep last 5000 experiences
        if len(self._experiences) > 5000:
            self._experiences = self._experiences[-5000:]
        self._save(self._experiences, self.experiences_file)
        # Detect patterns from new experience
        self._detect_pattern(experience)
        return exp_id

    def learn_from_success(self, experience_id: str, improvement_notes: str = '') -> bool:
        """Mark experience as a success and reinforce the strategy."""
        for exp in reversed(self._experiences):
            if exp['id'] == experience_id:
                exp['success'] = True
                exp['confidence'] = min(1.0, exp.get('confidence', 0.5) + 0.1)
                exp['improvement_notes'] = improvement_notes
                self._save(self._experiences, self.experiences_file)
                return True
        return False

    def learn_from_failure(self, experience_id: str, error_type: str, correction: str = '') -> bool:
        """Learn from a failure to avoid repeating mistakes."""
        for exp in reversed(self._experiences):
            if exp['id'] == experience_id:
                exp['success'] = False
                exp['confidence'] = max(0.1, exp.get('confidence', 0.5) - 0.2)
                exp['error_type'] = error_type
                exp['correction'] = correction
                self._save(self._experiences, self.experiences_file)
                # Record in failure patterns
                self._record_failure_pattern(exp)
                return True
        return False

    def _detect_pattern(self, experience: Dict) -> Optional[str]:
        """Detect if this experience matches a known pattern."""
        context = experience['context'].lower()
        action = experience['action'].lower()
        # Simple pattern: same context + different action outcomes
        for pattern in self._patterns[-20:]:  # Check recent patterns
            if (pattern['context_keywords'] and
                any(kw in context for kw in pattern['context_keywords'])):
                pattern['occurrence_count'] += 1
                if experience['success']:
                    pattern['success_count'] += 1
                self._save(self._patterns, self.patterns_file)
                return pattern['id']
        return None

    def _record_failure_pattern(self, experience: Dict) -> str:
        """Record a failure pattern to avoid repeating."""
        context = experience['context']
        keywords = [w for w in context.split() if len(w) > 4][:5]
        pattern_id = str(uuid.uuid4())
        pattern = {
            'id': pattern_id,
            'context_keywords': keywords,
            'action': experience['action'],
            'failure_reason': experience.get('error_type', 'unknown'),
            'occurrence_count': 1,
            'success_count': 0,
            'first_seen': experience['timestamp'],
        }
        self._patterns.append(pattern)
        self._save(self._patterns, self.patterns_file)
        return pattern_id

    def get_similar_experiences(self, context: str, limit: int = 5) -> List[Dict]:
        """Find similar past experiences for few-shot learning."""
        q = context.lower()
        scored = []
        for exp in self._experiences[-500:]:
            score = 0
            if any(w in exp['context'].lower() for w in q.split() if len(w) > 3):
                score += 1
            if exp['action'].lower() in q:
                score += 2
            score += exp.get('confidence', 0.5)
            scored.append((score, exp))
        scored.sort(key=lambda x: -x[0])
        return [exp for _, exp in scored[:limit]]

    def get_success_rate(self, manager: str = None) -> float:
        """Calculate success rate, optionally filtered by manager."""
        exps = self._experiences[-200:]
        if manager:
            exps = [e for e in exps if e.get('manager_used') == manager]
        if not exps:
            return 0.0
        return sum(1 for e in exps if e.get('success')) / len(exps)

    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics."""
        exps = self._experiences
        recent = [e for e in exps if datetime.fromisoformat(e['timestamp']) >=
                 datetime.now().replace(hour=0, minute=0, second=0)]
        return {
            'total_experiences': len(exps),
            'today_experiences': len(recent),
            'overall_success_rate': self.get_success_rate(),
            'total_patterns': len(self._patterns),
            'average_execution_time': sum(e.get('execution_time', 0) for e in exps) / max(1, len(exps)),
        }


_engine: Optional[LearningEngine] = None


def get_learning_engine() -> LearningEngine:
    global _engine
    if _engine is None:
        _engine = LearningEngine()
    return _engine
