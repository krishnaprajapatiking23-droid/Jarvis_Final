import brains_v2.tools

from brains_v2.tools.manager import process

tests = [

    "Open Notepad",

    "25+25",

    "https://google.com"

]

for command in tests:

    print()

    print(process(command))