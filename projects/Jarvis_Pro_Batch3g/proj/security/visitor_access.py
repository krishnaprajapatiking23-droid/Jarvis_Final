class Visitor:

    def __init__(self, name):

        self.name = name
        self.owner = False

    def grant_owner(self):

        self.owner = True

    def is_owner(self):

        return self.owner