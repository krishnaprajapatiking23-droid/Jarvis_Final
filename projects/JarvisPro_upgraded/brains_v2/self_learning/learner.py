from brains_v2.self_learning.storage import load_data, save_data
from datetime import datetime


def learn(command, decision, success):
    data = load_data()

    record = {
        "command": command,
        "decision": decision,
        "success": success,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # BUG FIX: this assumed load_data() always returns a dict that already
    # contains a "commands" list. An empty or newly created store raised
    # KeyError: 'commands' and took down the whole command pipeline -- a
    # learning side-effect must never be able to break a reply.
    if not isinstance(data, dict):
        data = {}

    commands = data.get("commands")

    if not isinstance(commands, list):
        commands = []
        data["commands"] = commands

    commands.append(record)

    save_data(data)