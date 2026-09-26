class DecisionTree:

    def decide(self, command):

        text = command.lower()

        if any(word in text for word in [

            "open",

            "launch",

            "run"

        ]):

            return "AUTOMATION"

        if any(word in text for word in [

            "build",

            "create",

            "develop",

            "design"

        ]):

            return "PROJECT"

        if any(word in text for word in [

            "remember",

            "save"

        ]):

            return "MEMORY"

        return "CHAT"


decision_tree = DecisionTree()