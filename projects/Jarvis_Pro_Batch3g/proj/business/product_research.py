from business.ai import ask_business


def research_product(command):

    prompt = f"""
You are an expert Shopify product researcher.

Analyze the following request:

{command}

Give:

1. Demand
2. Competition
3. Profit Potential
4. Target Audience
5. Selling Angle
6. Risk
7. Overall Score out of 10
"""

    return ask_business(prompt)