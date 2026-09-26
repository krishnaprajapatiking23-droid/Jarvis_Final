from business.ai import ask_business


def competitor_analysis(command):

    prompt = f"""
You are an e-commerce competitor analyst.

{command}

Analyze:

1. Main Competitors
2. Strengths
3. Weaknesses
4. Pricing Strategy
5. Marketing Strategy
6. Opportunities
7. Recommendations
"""

    return ask_business(prompt)