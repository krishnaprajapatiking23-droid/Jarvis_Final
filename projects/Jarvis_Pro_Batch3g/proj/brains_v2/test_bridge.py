from brains_v2.agent_bridge import bridge

tests = [

    "Open Notepad",

    "25+25",

    "Research SpaceX",

    "Write Python code",

    "Hello"

]

for command in tests:

    print()

    print(command)

    print(bridge.process(command))