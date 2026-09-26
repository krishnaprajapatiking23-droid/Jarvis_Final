import psutil


def app_running(app_name):

    app_name = app_name.lower()

    for process in psutil.process_iter(["name"]):

        try:

            name = process.info["name"]

            if name and app_name in name.lower():

                return True

        except Exception:
            pass

    return False