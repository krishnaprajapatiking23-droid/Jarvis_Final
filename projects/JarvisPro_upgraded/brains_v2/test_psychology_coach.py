"""Manual check for the psychology coach.

BUG FIX: this lived at ``brains_v2/test.py`` and did
``from psychology.coach import PersonalCoach``. There is no top-level
``psychology`` package -- the module is ``brains_v2.psychology.coach`` -- so
the file raised ModuleNotFoundError on import. Worse, its filename collided
with the ``brains_v2/test/`` package, so ``python -m brains_v2.test.<name>``
resolved to this broken module instead of the package. Renamed and repaired.
"""

from __future__ import annotations

from brains_v2.psychology.coach import PersonalCoach

SAMPLES = (
    "I am very happy today",
    "I failed my exam",
    "I hate everything",
    "I am nervous about tomorrow",
    "I am ready to win",
)


def run() -> None:
    coach = PersonalCoach()
    for text in SAMPLES:
        print("=" * 70)
        print("INPUT :", text)
        print("RESULT:", coach.coach(text))


if __name__ == "__main__":
    run()
