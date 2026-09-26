import pytesseract

from PIL import Image


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def read(path):

    image = Image.open(path)

    text = pytesseract.image_to_string(image)

    return text