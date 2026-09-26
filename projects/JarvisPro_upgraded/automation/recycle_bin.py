import os
from send2trash import send2trash


def delete_file(path):

    if not os.path.exists(path):
        return "File not found."

    try:

        send2trash(path)

        return f"Moved to Recycle Bin: {path}"

    except Exception as e:

        return f"Error: {e}"


def delete_folder(path):

    if not os.path.exists(path):
        return "Folder not found."

    try:

        send2trash(path)

        return f"Moved to Recycle Bin: {path}"

    except Exception as e:

        return f"Error: {e}"


def restore():

    return (
        "Files moved to the Recycle Bin must be restored "
        "manually through the operating system."
    )


def empty():

    return (
        "Emptying the Recycle Bin is not implemented yet."
    )