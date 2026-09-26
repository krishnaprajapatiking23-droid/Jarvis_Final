from brains_v2.vision.screen_reader import read_screen
from brains_v2.vision.image_analyzer import analyze


def see():

    data = read_screen()

    result = analyze(data["image"])

    return {

        "capture": data,

        "analysis": result

    }