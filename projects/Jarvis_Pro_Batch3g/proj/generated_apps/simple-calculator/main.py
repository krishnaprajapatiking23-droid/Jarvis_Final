import tkinter as tk

class CalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Calculator")
        self.root.geometry("300x400")
        self.expression = ""
        self.result_var = tk.StringVar()

        self.display = tk.Entry(root, textvariable=self.result_var, font=('Arial', 20), borderwidth=5)
        self.display.grid(row=0, column=0, columnspan=4)

        self.create_buttons()

    def create_buttons(self):
        buttons = [
            ('7', 1, 0), ('8', 1, 1), ('9', 1, 2), ('/', 1, 3),
            ('4', 2, 0), ('5', 2, 1), ('6', 2, 2), ('*', 2, 3),
            ('1', 3, 0), ('2', 3, 1), ('3', 3, 2), ('-', 3, 3),
            ('0', 4, 0), ('.', 4, 1), ('=', 4, 2), ('+', 4, 3),
            ('C', 5, 0)
        ]
        for text, row, col in buttons:
            btn = tk.Button(self.root, text=text, padx=20, pady=20, font=('Arial', 15), command=lambda t=text: self.button_click(t))
            btn.grid(row=row, column=col)

    def button_click(self, value):
        if value == 'C':
            self.expression = ""
            self.result_var.set("")
        elif value == '=':
            try:
                result = eval(self.expression)
                self.expression = str(result)
                self.result_var.set(result)
            except:
                self.result_var.set("Error")
        else:
            self.expression += value
            self.result_var.set(self.expression)

if __name__ == "__main__":
    root = tk.Tk()
    app = CalculatorApp(root)
    root.mainloop()