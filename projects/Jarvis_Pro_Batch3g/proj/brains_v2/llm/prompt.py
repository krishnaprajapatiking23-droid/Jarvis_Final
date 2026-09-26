"""
Prompt Builder
"""

from conversation.identity import identity


class PromptBuilder:

    def build(

        self,

        command,

        memory=None,

        context=None

    ):

        owner = identity.owner()

        owner_line = f"Owner is {owner}." if owner else ""

        prompt = f"""

You are Jarvis.

{owner_line}

Answer naturally.

User:

{command}

"""

        return prompt


prompt_builder = PromptBuilder()