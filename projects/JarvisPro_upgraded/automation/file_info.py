import os
import time


def get_info(path):

    if not os.path.exists(path):

        return "Path not found."

    stat = os.stat(path)

    return {

        "name": os.path.basename(path),

        "path": os.path.abspath(path),

        "type": "Folder" if os.path.isdir(path) else "File",

        "size": stat.st_size,

        "created": time.ctime(stat.st_ctime),

        "modified": time.ctime(stat.st_mtime),

        "accessed": time.ctime(stat.st_atime),

        "extension": os.path.splitext(path)[1]

    }


def file_exists(path):

    return os.path.exists(path)


def is_file(path):

    return os.path.isfile(path)


def is_folder(path):

    return os.path.isdir(path)


def file_size(path):

    if not os.path.exists(path):

        return 0

    return os.path.getsize(path)


def extension(path):

    return os.path.splitext(path)[1]