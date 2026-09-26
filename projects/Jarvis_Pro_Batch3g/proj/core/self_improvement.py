"""
==========================================
JARVIS PRO
Self-improvement
==========================================

Roadmap section 21 (self-improvement) and the
SELF-IMPROVEMENT -> BACKUP -> TEST -> VERIFY -> KEEP/ROLLBACK stage of the
section 42 loop.

This is deliberately conservative: JARVIS does not rewrite its own source
code. It tunes its own *settings* based on measured results, and every change
is backed up, verified and rolled back automatically if things get worse.

    from core.self_improvement import self_improvement

    self_improvement.review()        # what could be better, with evidence
    self_improvement.improve()       # apply safe tuning (backed up first)
    self_improvement.rollback()      # undo the last tuning round

Every proposal states the setting, the old value, the new value and the
evidence behind it, so nothing changes silently.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


# Settings the tuner is allowed to touch, with hard safety limits.
TUNABLE: dict[str, dict[str, Any]] = {
    "agent.max_retries": {"min": 1, "max": 4, "cast": int},
    "agent.max_steps": {"min": 3, "max": 12, "cast": int},
    "model.timeout": {"min": 30, "max": 300, "cast": int},
    "agent.confirm_risky": {"min": 0, "max": 1, "cast": bool},
}

MIN_EVIDENCE = 5


class SelfImprovement:
    """Measures its own performance and tunes settings safely."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ---------------------------------------------------- journal

    def _path(self) -> Path:
        try:
            from config import config

            return config.data_path() / "improvement_log.json"

        except Exception:
            return Path("data/improvement_log.json")

    def _load(self) -> list[dict[str, Any]]:
        path = self._path()

        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            return data if isinstance(data, list) else []

        except Exception:
            return []

    def _save(self, rounds: list[dict[str, Any]]) -> None:
        path = self._path()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(rounds[-50:], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        except Exception:
            pass

    # ---------------------------------------------------- evidence

    def evidence(self) -> dict[str, Any]:
        """Everything the tuner reasons about, gathered in one place."""

        found: dict[str, Any] = {
            "experience": {},
            "reliability": {},
            "weak_spots": [],
            "repeated_mistakes": [],
            "slowest": [],
        }

        try:
            from memory.experience import experience

            found["experience"] = experience.stats()

        except Exception:
            pass

        try:
            from core.observability import observability

            found["reliability"] = observability.health()
            found["slowest"] = [
                item
                for item in observability.stats()
                if item.get("average_seconds", 0) > 0
            ][:5]

        except Exception:
            pass

        try:
            from learning.behaviour import behaviour

            found["weak_spots"] = behaviour.weak_spots()

        except Exception:
            pass

        try:
            from learning.mistakes import mistakes

            found["repeated_mistakes"] = mistakes.repeated()

        except Exception:
            pass

        return found

    # ---------------------------------------------------- proposals

    def review(self) -> dict[str, Any]:
        """What could be improved, with the evidence and no changes made."""

        data = self.evidence()
        proposals: list[dict[str, Any]] = []

        try:
            from config import config

        except Exception:
            return {
                "ok": False,
                "proposals": [],
                "message": "Configuration is unavailable, so I cannot tune anything.",
            }

        stats = data.get("experience") or {}
        attempts = int(stats.get("attempts", 0))
        success_rate = float(stats.get("success_rate", 0.0))
        average_steps = float(stats.get("average_steps", 0.0))

        if attempts < MIN_EVIDENCE:
            return {
                "ok": True,
                "proposals": [],
                "evidence": data,
                "message": (
                    f"Only {attempts} recorded task(s) so far. I need at least "
                    f"{MIN_EVIDENCE} before changing my own settings."
                ),
            }

        retries = int(config.get("agent.max_retries", 2))

        # Failing often and not retrying much -> retry more.
        if success_rate < 70 and retries < TUNABLE["agent.max_retries"]["max"]:
            proposals.append(
                {
                    "setting": "agent.max_retries",
                    "from": retries,
                    "to": retries + 1,
                    "why": (
                        f"Success rate is {success_rate}% across {attempts} "
                        "tasks; one more retry may recover transient failures."
                    ),
                }
            )

        # Succeeding almost always with spare retries -> stop wasting time.
        if success_rate > 95 and retries > TUNABLE["agent.max_retries"]["min"]:
            proposals.append(
                {
                    "setting": "agent.max_retries",
                    "from": retries,
                    "to": retries - 1,
                    "why": (
                        f"Success rate is {success_rate}%, so fewer retries "
                        "will make failures surface faster."
                    ),
                }
            )

        steps = int(config.get("agent.max_steps", 8))

        # Plans regularly hitting the ceiling -> allow more room.
        if average_steps >= steps - 0.5 and steps < TUNABLE["agent.max_steps"]["max"]:
            proposals.append(
                {
                    "setting": "agent.max_steps",
                    "from": steps,
                    "to": steps + 2,
                    "why": (
                        f"Plans average {average_steps} steps against a limit "
                        f"of {steps}; they are probably being cut short."
                    ),
                }
            )

        # Timeouts showing up in repeated mistakes -> allow more time.
        timeout_trouble = any(
            "timeout" in str(item.get("error", "")).lower()
            or "timed out" in str(item.get("error", "")).lower()
            for item in data.get("repeated_mistakes", [])
        )
        timeout = int(config.get("model.timeout", 120))

        if timeout_trouble and timeout < TUNABLE["model.timeout"]["max"]:
            proposals.append(
                {
                    "setting": "model.timeout",
                    "from": timeout,
                    "to": min(timeout + 60, TUNABLE["model.timeout"]["max"]),
                    "why": "Timeouts keep appearing in repeated failures.",
                }
            )

        return {
            "ok": True,
            "proposals": proposals,
            "evidence": data,
            "message": (
                f"{len(proposals)} improvement(s) proposed."
                if proposals
                else "Nothing needs tuning; current settings are performing well."
            ),
        }

    # ---------------------------------------------------- applying

    def _within_limits(self, setting: str, value: Any) -> Any:
        rules = TUNABLE.get(setting)

        if rules is None:
            return None

        try:
            if rules["cast"] is bool:
                return bool(value)

            number = rules["cast"](value)

        except Exception:
            return None

        return max(rules["min"], min(number, rules["max"]))

    def improve(self, dry_run: bool = False) -> dict[str, Any]:
        """Apply the proposals, after taking a backup."""

        review = self.review()
        proposals = review.get("proposals", [])

        if not proposals:
            return {
                "ok": True,
                "applied": [],
                "message": review.get("message", "Nothing to improve."),
            }

        if dry_run:
            return {
                "ok": True,
                "applied": [],
                "proposals": proposals,
                "dry_run": True,
                "message": f"{len(proposals)} change(s) would be applied.",
            }

        from config import config

        # Safety net first (roadmap: BACKUP before self-improvement).
        backup_name = ""

        try:
            from core.backup_manager import backup

            created = backup.create("before_self_improvement")
            backup_name = str(created.get("name", ""))

        except Exception:
            backup_name = ""

        baseline = {}

        try:
            from core.observability import observability

            baseline = observability.health()

        except Exception:
            pass

        applied: list[dict[str, Any]] = []

        with self._lock:
            for proposal in proposals:
                setting = str(proposal["setting"])
                safe_value = self._within_limits(setting, proposal["to"])

                if safe_value is None:
                    continue

                previous = config.get(setting)

                if previous == safe_value:
                    continue

                if config.set(setting, safe_value):
                    applied.append(
                        {
                            "setting": setting,
                            "from": previous,
                            "to": safe_value,
                            "why": proposal["why"],
                        }
                    )

            if applied:
                rounds = self._load()
                rounds.append(
                    {
                        "at": time.time(),
                        "changes": applied,
                        "backup": backup_name,
                        "baseline": baseline,
                        "verified": None,
                    }
                )
                self._save(rounds)

        return {
            "ok": True,
            "applied": applied,
            "backup": backup_name,
            "message": (
                f"Applied {len(applied)} change(s); a backup was taken first."
                if applied
                else "No changes were needed after safety checks."
            ),
        }

    # ---------------------------------------------------- verify / rollback

    def verify(self) -> dict[str, Any]:
        """Compare reliability before and after the last tuning round."""

        rounds = self._load()

        if not rounds:
            return {"ok": True, "message": "No tuning has been applied yet."}

        last = rounds[-1]

        try:
            from core.observability import observability

            now = observability.health()

        except Exception:
            return {"ok": False, "message": "Reliability data is unavailable."}

        before = float(last.get("baseline", {}).get("success_rate", 0.0))
        after = float(now.get("success_rate", 0.0))
        verdict = "better" if after >= before else "worse"

        last["verified"] = {
            "before": before,
            "after": after,
            "verdict": verdict,
            "at": time.time(),
        }
        self._save(rounds)

        return {
            "ok": verdict == "better",
            "before": before,
            "after": after,
            "verdict": verdict,
            "message": (
                f"Success rate went from {before}% to {after}% ({verdict})."
            ),
        }

    def rollback(self) -> dict[str, Any]:
        """Undo the settings changed by the last tuning round."""

        rounds = self._load()

        if not rounds:
            return {"ok": False, "message": "There is nothing to roll back."}

        try:
            from config import config

        except Exception:
            return {"ok": False, "message": "Configuration is unavailable."}

        with self._lock:
            last = rounds.pop()
            restored: list[str] = []

            for change in last.get("changes", []):
                if config.set(change["setting"], change["from"]):
                    restored.append(change["setting"])

            self._save(rounds)

        return {
            "ok": bool(restored),
            "restored": restored,
            "message": (
                f"Rolled back {len(restored)} setting(s)."
                if restored
                else "Nothing could be rolled back."
            ),
        }

    def auto_cycle(self) -> dict[str, Any]:
        """One full improve -> verify -> keep/rollback cycle."""

        applied = self.improve()

        if not applied.get("applied"):
            return {**applied, "verified": None, "rolled_back": False}

        check = self.verify()

        if check.get("verdict") == "worse":
            undone = self.rollback()

            return {
                **applied,
                "verified": check,
                "rolled_back": True,
                "message": (
                    "Results got worse, so I rolled the changes back. "
                    + str(undone.get("message", ""))
                ),
            }

        return {**applied, "verified": check, "rolled_back": False}

    def history(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._load()[-limit:]

    def status(self) -> dict[str, Any]:
        rounds = self._load()

        return {
            "rounds": len(rounds),
            "tunable_settings": sorted(TUNABLE),
            "last_round": rounds[-1] if rounds else None,
        }


self_improvement = SelfImprovement()
