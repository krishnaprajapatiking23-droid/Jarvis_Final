from conversation.identity import identity

class UserProfile:

    def __init__(self):

        self.name = identity.owner()

        self.interests = []

        self.skills = []

        self.projects = []

    def add_interest(self, value):

        if value not in self.interests:

            self.interests.append(value)

    def add_skill(self, value):

        if value not in self.skills:

            self.skills.append(value)

    def add_project(self, value):

        if value not in self.projects:

            self.projects.append(value)

    def data(self):

        return {

            "name": self.name,

            "interests": self.interests,

            "skills": self.skills,

            "projects": self.projects

        }


profile = UserProfile()