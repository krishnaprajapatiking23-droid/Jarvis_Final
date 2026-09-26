from security.safe_math import evaluate
def process_math(command):
 text=str(command or '')
 if not text.lower().startswith('calculate'):return None
 try:return f"The answer is {evaluate(text[9:].strip())}"
 except Exception as e:return f"Invalid mathematical expression: {e}"
