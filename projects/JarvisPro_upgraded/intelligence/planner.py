def create_plan(request_type):

    plans = {

        "automation": [
            "Execute Command"
        ],

        "business": [
            "Business Agent"
        ],

        "coding": [
            "Coding Agent"
        ],

        "mission": [
            "Mission Planner"
        ],

        "chat": [
            "Conversation Brain"
        ]

    }

    return plans.get(request_type, ["Conversation Brain"])