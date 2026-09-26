from security.safe_math import evaluate
def calculate(command):
 try:return evaluate(command)
 except Exception as e:return {'success':False,'error':str(e)}
