from conversation.identity import identity

class Relationship:

    def __init__(self):

        self.owner = identity.owner()

        self.trust = 100

        self.friendship = 1

        self.total_talks = 0

    def talk(self):

        self.total_talks += 1

        if self.total_talks % 10 == 0:

            self.friendship += 1

    def data(self):

        return {

            "owner": self.owner,

            "trust": self.trust,

            "friendship": self.friendship,

            "talks": self.total_talks

        }


relationship = Relationship()