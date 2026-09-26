from brains_v2.vision_v2.screenshot import capture
from brains_v2.vision_v2.ocr import read
from brains_v2.vision_v2.analyzer import analyze


def see():

    image = capture()

    text = read(image)

    answer = analyze(text)

    return {

        "image": image,

        "ocr": text,

        "analysis": answer

    }