import time

from scheduler.reminder_checker import check_reminders
from scheduler.notification import notify


def start_scheduler():

    print("Scheduler Started...")

    while True:

        reminders = check_reminders()

        for reminder in reminders:

            notify(reminder)

        time.sleep(30)