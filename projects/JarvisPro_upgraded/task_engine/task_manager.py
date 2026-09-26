tasks = []


def add(task):

    tasks.append({
        "task": task,
        "status": "Running"
    })


def complete(task):

    for t in tasks:

        if t["task"] == task:
            t["status"] = "Done"


def clear():

    tasks.clear()


def get():

    return tasks