class ActionPipeline:

    def __init__(self):

        self.pipeline = []

    def add(self, action):

        self.pipeline.append({

            "action": action,

            "status": "Pending"

        })

    def complete(self):

        if self.pipeline:

            self.pipeline[0]["status"] = "Completed"

    def next(self):

        if not self.pipeline:

            return None

        return self.pipeline[0]

    def clear_completed(self):

        self.pipeline = [

            item

            for item in self.pipeline

            if item["status"] != "Completed"

        ]

    def data(self):

        return self.pipeline


pipeline = ActionPipeline()