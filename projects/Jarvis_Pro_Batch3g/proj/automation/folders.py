import os
import subprocess

# Get the current user's home directory
HOME = os.path.expanduser("~")

# Folder paths
FOLDERS = {
    "desktop": os.path.join(HOME, "OneDrive", "Desktop"),
    "downloads": os.path.join(HOME, "Downloads"),
    "documents": os.path.join(HOME, "Documents"),
    "pictures": os.path.join(HOME, "Pictures"),
    "videos": os.path.join(HOME, "Videos"),
    "music": os.path.join(HOME, "Music"),

    # Your project
    "jarvis project": r"C:\Users\Yogi\OneDrive\Desktop\Jarvis_Pro"
}


def open_folder(command):

    command = command.lower().strip()

    for folder_name, folder_path in FOLDERS.items():

        if folder_name in command:

            if os.path.exists(folder_path):

                subprocess.Popen(["explorer", folder_path])

                return f"Opening {folder_name.title()}."

            else:

                return f"{folder_name.title()} folder was not found."

    return None