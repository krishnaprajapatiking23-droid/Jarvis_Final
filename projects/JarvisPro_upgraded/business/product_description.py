from business.ai import ask_business


def create_description(command):

    prompt = f"""
You are an expert Shopify copywriter.

Create a high-converting product description.

Product:

{command}

Include:

1. Product Title
2. Short Description
3. Benefits
4. Features
5. Why Buy
6. Call To Action
"""

    return ask_business(prompt)