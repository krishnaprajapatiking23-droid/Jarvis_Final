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

    data["commands"].append(record)

    save_data(data)