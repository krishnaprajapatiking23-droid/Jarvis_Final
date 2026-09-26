"""
LLM Chat
"""

from .provider import llm
from .prompt import prompt_builder


class ChatAI:

    def chat(self, command):

        prompt = prompt_builder.build(command)

        return llm.ask(prompt)


chat_ai = ChatAI()