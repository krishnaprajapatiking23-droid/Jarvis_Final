from datetime import datetime

session = {
    "user": "",
    "start_time": None,
    "questions": 0,
    "apps_opened": 0,
    "folders_created": 0,
    "goals_added": 0
}


def start_session(username):

    session["user"] = username
    session["start_time"] = datetime.now()

    session["questions"] = 0
    session["apps_opened"] = 0
    session["folders_created"] = 0
    session["goals_added"] = 0


def add_question():

    session["questions"] += 1


def add_app():

    session["apps_opened"] += 1


def add_folder():

    session["folders_created"] += 1


def add_goal():

    session["goals_added"] += 1


def end_session():

    end = datetime.now()

    duration = end - session["start_time"]

    return {
        "user": session["user"],
        "duration": str(duration).split(".")[0],
        "questions": session["questions"],
        "apps": session["apps_opened"],
        "folders": session["folders_created"],
        "goals": session["goals_added"]
    }