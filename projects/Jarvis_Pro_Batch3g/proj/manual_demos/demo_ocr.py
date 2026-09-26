from vision.screenshot import take_screenshot
from vision.ocr import read_text

image = take_screenshot()

text = read_text(image)

print("\n===== SCREEN TEXT =====\n")
print(text)