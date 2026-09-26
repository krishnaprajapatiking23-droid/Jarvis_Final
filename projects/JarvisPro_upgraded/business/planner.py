from business.manager import business_manager


def execute_business_plan(command):

    steps = []

    text = command.lower()

    if any(word in text for word in [
        "shopify",
        "business",
        "launch",
        "sell"
    ]):

        steps = [
            "Research Product",
            "Analyze Competitors",
            "Find Target Audience",
            "Calculate Pricing",
            "Calculate Profit",
            "Generate Product Description",
            "Generate Meta Ads",
            "Create Launch Strategy"
        ]

    results = {}

    for step in steps:

        print(f"\nExecuting: {step}")

        if step == "Research Product":
            results[step] = business_manager("research product " + command)

        elif step == "Analyze Competitors":
            results[step] = business_manager("competitor " + command)

        elif step == "Find Target Audience":
            results[step] = business_manager("audience " + command)

        elif step == "Calculate Pricing":
            results[step] = business_manager("price " + command)

        elif step == "Calculate Profit":
            results[step] = business_manager("profit " + command)

        elif step == "Generate Product Description":
            results[step] = business_manager("description " + command)

        elif step == "Generate Meta Ads":
            results[step] = business_manager("meta ads " + command)

        elif step == "Create Launch Strategy":
            results[step] = business_manager("strategy " + command)

    return results

# BUG FIX: manual_demos/demo_planner.py imported ``create_business_plan``,
# which was never defined -- only ``execute_business_plan`` existed.


def create_business_plan(command):
    """Build a structured plan for a business goal.

    Returns the planner's step list so callers get something inspectable
    rather than a printed blob.
    """
    from brains_v2.ai.planner import planner

    built = planner.create(str(command or ""))
    built["rendered"] = planner.render(built)
    return built
