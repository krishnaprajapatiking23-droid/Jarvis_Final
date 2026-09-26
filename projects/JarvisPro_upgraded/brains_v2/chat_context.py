class ChatContext:

    def __init__(self):

        self.last_topic = ""

        self.last_question = ""

        self.last_answer = ""

    def update(self, command, reply):

        self.last_question = command

        self.last_answer = reply

        text = command.lower()

        if "notepad" in text:

            self.last_topic = "notepad"

        elif "calculator" in text:

            self.last_topic = "calculator"

        elif "paint" in text:

            self.last_topic = "paint"

        elif "jarvis" in text:

            self.last_topic = "jarvis"

    def data(self):

        return {

            "topic": self.last_topic,

            "question": self.last_question,

            "answer": self.last_answer

        }


chat_context = ChatContext()