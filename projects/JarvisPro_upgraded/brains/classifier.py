def classify_brain(command):

    text = command.lower()

    business = [
        "shopify",
        "product",
        "ads",
        "profit",
        "audience",
        "pricing",
        "competitor",
        "business"
    ]

    coding = [
        "python",
        "code",
        "debug",
        "error",
        "function",
        "class",
        "program"
    ]

    vision = [
        "image",
        "photo",
        "screenshot",
        "picture",
        "vision"
    ]

    for word in business:
        if word in text:
            return "business"

    for word in coding:
        if word in text:
            return "coding"

    for word in vision:
        if word in text:
            return "vision"

    return "chat"