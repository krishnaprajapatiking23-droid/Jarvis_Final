from conversation.manager import add_history

from conversation.recall import last_message


add_history(

    "Open Notepad",

    "Krishna, I've opened Notepad."

)

add_history(

    "Save it",

    "Saving the Notepad file."

)

print(last_message())