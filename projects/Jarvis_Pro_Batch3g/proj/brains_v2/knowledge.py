class Knowledge:

    def __init__(self):

        self.data = {}

    def remember(self, key, value):

        self.data[key.lower()] = value

    def recall(self, key):

        return self.data.get(key.lower())

    def exists(self, key):

        return key.lower() in self.data

    def all(self):

        return self.data


knowledge = Knowledge()