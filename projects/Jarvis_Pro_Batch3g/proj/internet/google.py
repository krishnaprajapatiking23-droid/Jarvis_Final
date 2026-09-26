import webbrowser
import urllib.parse


def google_search(query):

    query = query.strip()

    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)

    webbrowser.open(url)

    return f"Searching Google for '{query}'."