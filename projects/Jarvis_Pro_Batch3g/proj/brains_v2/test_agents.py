import brains_v2.agents

from brains_v2.agents.manager import process

tests = [

    "Write Python code",

    "Research SpaceX",

    "Plan my project",

    "Open Notepad",

    "Hello Jarvis"

]

for command in tests:

    print(process(command))