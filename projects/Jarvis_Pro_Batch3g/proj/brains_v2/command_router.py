from brains_v2.llm.manager import ask
from brains_v2.memory import memory_intent
from brains_v2.automation import execute


EXIT_WORDS = [

    "exit",

    "quit",

    "shutdown",

    "bye",

    "goodbye",

    "jarvis shutdown"

]


class CommandRouter:

    def route(self, command, decision):

        text = command.lower()

        if any(word in text for word in EXIT_WORDS):

            return {

                "type": "exit",

                "reply": "Goodbye."

            }

        if "remember" in text:

            if "my company is" in text:

                company = command.split("is",1)[1].strip()

                memory_intent.add(

                    "company",

                    company

                )

                return {

                    "type":"memory",

                    "reply":f"I'll remember that your company is {company}."

                }

            memory_intent.add(command, "Saved")

            return {

                "type": "memory",

                "reply": "I will remember that."

            }

        if any(word in text for word in [

            "open",

            "launch",

            "run"

        ]):

            result = execute(command, decision)

            return {

                "type": "automation",

                "result": result

            }

        if any(word in text for word in [

            "what",

            "who",

            "why",

            "how",

            "when",

            "where",

            "explain",

            "tell"

        ]):

            return {

                "type": "llm",

                "reply": ask(command)

            }

        return {

            "type": "chat"

        }


router = CommandRouter()