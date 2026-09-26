import tkinter as tk

class Calculator:
    def __init__(self, master):
        self.master = master
        self.master.title("Simple Calculator")
        self.display = tk.Entry(master, width=20, font=('Arial', 14), borderwidth=2, relief='solid')
        self.display.grid(row=0, column=0, columnspan=4)
        self.display.insert(0, "0")

        self.create_buttons()

    def create_buttons(self):
        buttons = [
            'C', '7', '8', '9', '/',
            '4', '5', '6', '*',
            '1', '2', '3', '-',
            '0', '.', '=', '+'
        ]

        row = 1
        col = 0
        for button_text in buttons:
            if button_text == '=':
                cmd = self.equals
            elif button_text == 'C':
                cmd = self.clear
            elif button_text == '.':
                cmd = self.add_dot
            else:
                cmd = lambda t=button_text: self.button_click(t)
            
            btn = tk.Button(self.master, text=button_text, width=5, height=2, command=cmd)
            btn.grid(row=row, column=col)
            col += 1
            if col > 3:
                col = 0
                row += 1

    def button_click(self, char):
        current = self.display.get()
        if current == "0":
            self.display.delete(0, tk.END)
        self.display.insert(tk.END, char)

    def add_dot(self):
        current = self.display.get()
        if '.' not in current:
            self.display.insert(tk.END, '.')

    def clear(self):
        self.display.delete(0, tk.END)
        self.display.insert(0, "0")

    def equals(self):
        try:
            expression = self.display.get()
            result = eval(expression)
            self.display.delete(0, tk.END)
            self.display.insert(0, str(result))
        except:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")

if __name__ == "__main__":
    root = tk.Tk()
    calc = Calculator(root)
    root.mainloop()