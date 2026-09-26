from conversation.references import has_reference
from conversation.manager import current
from conversation.recall import last_message


def resolve(command):

    if has_reference(command):

        context = current()

        previous = last_message()

        return {

            "context": context,

            "previous": previous

        }

    return None