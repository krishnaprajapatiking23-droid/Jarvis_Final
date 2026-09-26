import tools.calculator

from tools.manager import execute

while True:

    expression = input("Expression : ")

    if expression.lower() == "exit":
        break

    print(execute("calculator", expression))