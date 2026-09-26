from security.safe_math import evaluate
class Calculator:
 name='calculator'
 def execute(self,expression):
  try:return {'success':True,'result':evaluate(expression)}
  except Exception as e:return {'success':False,'error':str(e)}
calculator=Calculator()
