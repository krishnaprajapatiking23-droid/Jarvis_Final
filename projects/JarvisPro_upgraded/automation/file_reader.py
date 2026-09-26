import os


def read_file(path):

    if not os.path.exists(path):
        return "File not found."

    if os.path.isdir(path):
        return "Path is a folder."

    try:

        with open(path, "r", encoding="utf-8") as file:

            return file.read()

    except UnicodeDecodeError:

        return "Unsupported text encoding."

    except Exception as e:

        return f"Error: {e}"


def read_lines(path):

    if not os.path.exists(path):
        return []

    try:

        with open(path, "r", encoding="utf-8") as file:

            return file.readlines()

    except Exception:

        return []


def read_first_line(path):

    lines = read_lines(path)

    if lines:

        return lines[0].strip()

    return ""


def read_last_line(path):

    lines = read_lines(path)

    if lines:

        return lines[-1].strip()

    return ""