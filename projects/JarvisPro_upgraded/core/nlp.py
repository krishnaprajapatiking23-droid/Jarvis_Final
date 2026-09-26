def contains_any(text, keywords):

    text = text.lower()

    return any(word in text for word in keywords)