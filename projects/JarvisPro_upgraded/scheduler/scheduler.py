import threading

from scheduler.scheduler_engine import start_scheduler


def run():

    thread = threading.Thread(
        target=start_scheduler,
        daemon=True
    )

    thread.start()