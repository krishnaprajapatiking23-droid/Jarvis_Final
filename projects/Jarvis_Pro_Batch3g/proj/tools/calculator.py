from security.safe_math import evaluate
def calculate(expression):
 try:return evaluate(expression)
 except Exception as e:return f'Calculation error: {e}'
