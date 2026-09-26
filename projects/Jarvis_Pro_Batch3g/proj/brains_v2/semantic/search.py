from brains_v2.semantic.database import memory


def search(query):

    query = query.lower()

    result = []

    for item in memory.all():

        if any(word in item.lower() for word in query.split()):

            result.append(item)

    return result