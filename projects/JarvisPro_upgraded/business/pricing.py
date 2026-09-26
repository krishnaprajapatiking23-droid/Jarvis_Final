from business.ai import ask_business


def calculate_price(command):

    prompt = f"""
You are an expert e-commerce pricing strategist.

Based on this request:

{command}

Calculate:

1. Selling Price
2. Profit
3. Profit Margin
4. Break-even ROAS
5. Suggested Discount
6. Final Recommendation
"""

    return ask_business(prompt)