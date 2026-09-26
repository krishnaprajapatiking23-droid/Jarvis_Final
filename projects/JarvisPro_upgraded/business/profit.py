from compat.ollama_safe import ollama
from core.config import CHAT_MODEL

def calculate_profit(command):

    prompt = f"""
You are an e-commerce profit expert.

{command}

Calculate:

1. Revenue
2. Cost
3. Gross Profit
4. Net Profit
5. Profit Margin
6. ROI
7. Break-even ROAS

Explain everything clearly.
"""

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]