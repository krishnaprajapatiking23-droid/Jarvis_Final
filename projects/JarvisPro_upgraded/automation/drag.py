import pyautogui
import time


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def drag_to(start_x, start_y, end_x, end_y, duration=0.5):

    pyautogui.moveTo(start_x, start_y)

    pyautogui.dragTo(end_x, end_y, duration=duration, button="left")

    return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})."


def drag_relative(dx, dy, duration=0.5):

    pyautogui.dragRel(dx, dy, duration=duration, button="left")

    return f"Dragged by ({dx}, {dy})."


def drag_horizontal(distance, duration=0.5):

    pyautogui.dragRel(distance, 0, duration=duration, button="left")

    return f"Dragged horizontally by {distance}px."


def drag_vertical(distance, duration=0.5):

    pyautogui.dragRel(0, distance, duration=duration, button="left")

    return f"Dragged vertically by {distance}px."


def hold_drag(start_x, start_y, end_x, end_y, hold_time=1, duration=0.5):

    pyautogui.moveTo(start_x, start_y)

    pyautogui.mouseDown()

    time.sleep(hold_time)

    pyautogui.moveTo(end_x, end_y, duration=duration)

    pyautogui.mouseUp()

    return "Hold drag completed."


def select_area(x1, y1, x2, y2):

    pyautogui.moveTo(x1, y1)

    pyautogui.dragTo(x2, y2, duration=0.4, button="left")

    return "Area selected."


def drag_image(image_path, end_x, end_y, confidence=0.9):

    location = pyautogui.locateCenterOnScreen(
        image_path,
        confidence=confidence
    )

    if location is None:

        return "Image not found."

    pyautogui.moveTo(location)

    pyautogui.dragTo(end_x, end_y, duration=0.5)

    return "Image dragged successfully."


def safe_drag(start_x, start_y, end_x, end_y):

    try:

        return drag_to(start_x, start_y, end_x, end_y)

    except Exception as e:

        return f"Error: {e}"