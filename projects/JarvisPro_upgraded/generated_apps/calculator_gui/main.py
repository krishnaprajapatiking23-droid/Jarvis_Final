import tkinter as tk

root = tk.Tk()
root.title("Calculator")

entry = tk.Entry(root, width=20, font=('Arial', 14))
entry.grid(row=0, column=0, columnspan=4)

buttons = [
    ['7', '8', '9', '/'],
    ['4', '5', '6', '*'],
    ['1', '2', '3', '-'],
    ['0', '.', '=', '+']
]

for i in range(4):
    for j in range(4):
        button = tk.Button(root, text=buttons[i][j], width=5, command=lambda text=buttons[i][j]: button_click(text))
        button.grid(row=i+1, column=j)

def button_click(text):
    if text == '=':
        try:
            expression = entry.get()
            result = eval(expression)
            entry.delete(0, tk.END)
            entry.insert(0, str(result))
        except:
            entry.delete(0, tk.END)
            entry.insert(0, "Error")
    else:
        current = entry.get()
        entry.delete(0, tk.END)
        entry.insert(0, current + text)

root.mainloop()