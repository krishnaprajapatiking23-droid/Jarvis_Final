from business.ai import ask_business


def ask_coding(prompt):

    system_prompt = f"""
You are an expert software engineer.

You specialize in:

- Python
- AI
- Machine Learning
- Ollama
- Automation
- Desktop Applications
- Debugging
- Refactoring
- Best Practices

Always explain clearly.

{prompt}
"""

    return ask_business(system_prompt)