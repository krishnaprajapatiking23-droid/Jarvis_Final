import os


def search_files(directory, keyword):

    results = []

    if not os.path.exists(directory):
        return results

    keyword = keyword.lower()

    for root, _, files in os.walk(directory):

        for file in files:

            if keyword in file.lower():

                results.append(
                    os.path.join(root, file)
                )

    return results


def search_extension(directory, extension):

    results = []

    if not os.path.exists(directory):
        return results

    extension = extension.lower()

    if not extension.startswith("."):
        extension = "." + extension

    for root, _, files in os.walk(directory):

        for file in files:

            if file.lower().endswith(extension):

                results.append(
                    os.path.join(root, file)
                )

    return results


def search_folders(directory, keyword):

    results = []

    if not os.path.exists(directory):
        return results

    keyword = keyword.lower()

    for root, folders, _ in os.walk(directory):

        for folder in folders:

            if keyword in folder.lower():

                results.append(
                    os.path.join(root, folder)
                )

    return results