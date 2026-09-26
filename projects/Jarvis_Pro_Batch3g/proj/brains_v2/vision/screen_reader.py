from brains_v2.vision.screenshot import capture


def read_screen():

    path = capture()

    return {

        "image": path,

        "status": "Captured"

    }