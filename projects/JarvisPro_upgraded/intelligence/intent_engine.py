def detect_request_type(command):

    text = command.lower()

    business = [
        "shopify",
        "product",
        "ads",
        "meta",
        "profit",
        "pricing",
        "audience",
        "competitor"
    ]

    coding = [
        "python",
        "code",
        "debug",
        "error",
        "bug",
        "function",
        "class"
    ]

    automation = [
        "open",
        "close",
        "create folder",
        "delete",
        "shutdown"
    ]

    mission = [
        "build",
        "launch",
        "start business",
        "grow business",
        "complete project"
    ]

    for word in automation:
        if word in text:
            return "automation"

    for word in business:
        if word in text:
            return "business"

    for word in coding:
        if word in text:
            return "coding"

    for word in mission:
        if word in text:
            return "mission"

    return "chat"