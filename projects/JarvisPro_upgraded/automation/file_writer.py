import os


def write_file(path, text):

    try:

        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:

            file.write(text)

        return f"File written successfully: {path}"

    except Exception as e:

        return f"Error: {e}"


def append_file(path, text):

    try:

        folder = os.path.dirname(path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(path, "a", encoding="utf-8") as file:

            file.write(text)

        return f"Text appended successfully: {path}"

    except Exception as e:

        return f"Error: {e}"


def overwrite_file(path, text):

    return write_file(path, text)


def clear_file(path):

    try:

        with open(path, "w", encoding="utf-8"):
            pass

        return f"File cleared: {path}"

    except Exception as e:

        return f"Error: {e}"