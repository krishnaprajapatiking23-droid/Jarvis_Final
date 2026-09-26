def create_mission(goal):

    text = goal.lower()

    tasks = []

    if any(word in text for word in [
        "shopify",
        "business",
        "sell",
        "launch",
        "ecommerce"
    ]):

        tasks = [
            "Research Product",
            "Analyze Competitors",
            "Find Target Audience",
            "Calculate Pricing",
            "Calculate Profit",
            "Generate Product Description",
            "Generate Meta Ads",
            "Create Business Strategy"
        ]

    elif any(word in text for word in [
        "python",
        "code",
        "program",
        "debug"
    ]):

        tasks = [
            "Analyze Problem",
            "Generate Code",
            "Debug Code",
            "Review Code"
        ]

    else:

        tasks = [
            "Understand Goal",
            "Answer User"
        ]

    return tasks