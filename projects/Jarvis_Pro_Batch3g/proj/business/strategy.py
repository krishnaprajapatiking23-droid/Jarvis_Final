from business.ai import ask_business


def business_strategy(command):

    prompt = f"""
You are a Shopify business consultant.

{command}

Create:

1. Launch Strategy
2. Marketing Strategy
3. Scaling Plan
4. Daily Tasks
5. Budget Recommendation
6. Risk Analysis
"""

    return ask_business(prompt)