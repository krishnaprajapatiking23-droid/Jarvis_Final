import tkinter as tk

class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")
        self.entry = tk.Entry(root, width=20, font=('Arial', 14))
        self.entry.grid(row=0, column=0, columnspan=4)

        buttons = [
            ['7', '8', '9', '/'],
            ['4', '5', '6', '*'],
            ['1', '2', '3', '-'],
            ['0', '.', '=', '+']
        ]

        for row in range(4):
            for col in range(4):
                text = buttons[row][col]
                if text == '=':
                    btn = tk.Button(root, text=text, width=5, height=2, command=self.calculate)
                elif text in ['+', '-', '*', '/']:
                    btn = tk.Button(root, text=text, width=5, height=2, command=lambda op=text: self.set_operator(op))
                else:
                    btn = tk.Button(root, text=text, width=5, height=2, command=lambda val=text: self.add_to_expression(val))
                btn.grid(row=row+1, column=col)

    def add_to_expression(self, value):
        self.entry.insert(tk.END, value)

    def set_operator(self, operator):
        current = self.entry.get()
        if current != '':
            self.entry.insert(tk.END, operator)

    def calculate(self):
        try:
            expression = self.entry.get()
            result = eval(expression)
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, str(result))
        except:
            self.entry.insert(tk.END, "Error")

if __name__ == "__main__":
    root = tk.Tk()
    app = Calculator(root)
    root.mainloop()