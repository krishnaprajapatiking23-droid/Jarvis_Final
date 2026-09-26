from brains_v2.manager import brain

brain.process("Open Notepad")

brain.process("Open Calculator")

brain.process("Hello")

data = brain.process("Open Paint")

print()

print(data["brain_state"])