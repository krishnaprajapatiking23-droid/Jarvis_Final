PLANS = {

    "OPEN": [
        "Understand the command",
        "Find the application",
        "Open the application",
        "Verify it opened",
        "Generate a response"
    ],

    "CREATE": [
        "Understand the request",
        "Create the item",
        "Verify creation",
        "Generate a response"
    ],

    "MEMORY": [
        "Extract information",
        "Store it",
        "Confirm storage"
    ],

    "CHAT": [
        "Understand message",
        "Generate reply"
    ]

}


def make_plan(decision):

    return PLANS.get(decision, [])