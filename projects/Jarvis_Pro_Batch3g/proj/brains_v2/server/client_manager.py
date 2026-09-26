"""
Client Manager
"""


class ClientManager:

    def __init__(self):

        self.clients = {}

    def add(

        self,

        token,

        device

    ):

        self.clients[token] = device

    def remove(

        self,

        token

    ):

        self.clients.pop(token, None)

    def count(self):

        return len(self.clients)

    def all(self):

        return self.clients


clients = ClientManager()