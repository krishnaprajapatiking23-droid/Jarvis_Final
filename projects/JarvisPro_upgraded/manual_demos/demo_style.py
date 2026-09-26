from emotion.response_style import style_answer

answer = "Your Notepad has been opened successfully."

print(style_answer(answer, "happy"))
print()
print(style_answer(answer, "frustrated"))
print()
print(style_answer(answer, "confused"))