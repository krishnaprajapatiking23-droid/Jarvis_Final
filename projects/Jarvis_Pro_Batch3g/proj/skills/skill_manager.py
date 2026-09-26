from skills.math import process_math
from skills.notes import process_notes
from skills.timer import process_timer
from skills.stopwatch import process_stopwatch
from skills.reminder import process_reminder


def process_skill(command):

    skills = [
        process_math,
        process_notes,
        process_timer,
        process_stopwatch,
        process_reminder,
    ]

    for skill in skills:

        result = skill(command)

        if result:
            return result

    return None