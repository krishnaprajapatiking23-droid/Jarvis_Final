import json
import os

DATA_FILE = "data/experience.json"


SCHEMA = {
    "commands": list,
    "statistics": dict,
    "mistakes": list,
    "successes": list,
    "predictions": dict,
    "habits": dict,
}


def _blank():
    return {key: kind() for key, kind in SCHEMA.items()}


def load_data():
    """Load the experience store, always with every expected key present.

    BUG FIX: the default schema was only returned when the file did not
    exist. An empty, truncated or partially written file was returned as-is,
    so callers doing ``data["commands"].append(...)`` raised KeyError and
    killed the command pipeline.
    """
    if not os.path.exists(DATA_FILE):
        return _blank()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return _blank()

    if not isinstance(data, dict):
        return _blank()

    for key, kind in SCHEMA.items():
        if not isinstance(data.get(key), kind):
            data[key] = kind()

    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)