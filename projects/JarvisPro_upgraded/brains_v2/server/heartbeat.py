"""
Heartbeat Monitor
"""

import threading
import time


class Heartbeat:

    def __init__(self):

        self.running = False

        self.clients = {}

    def add(

        self,

        token

    ):

        self.clients[token] = time.time()

    def remove(

        self,

        token

    ):

        self.clients.pop(token, None)

    def update(

        self,

        token

    ):

        self.clients[token] = time.time()

    def worker(self):

        while self.running:

            now = time.time()

            expired = []

            for token, last in self.clients.items():

                if now - last > 30:

                    expired.append(token)

            for token in expired:

                del self.clients[token]

            time.sleep(5)

    def start(self):

        if self.running:

            return

        self.running = True

        threading.Thread(

            target=self.worker,

            daemon=True

        ).start()

    def stop(self):

        self.running = False


heartbeat = Heartbeat()