import time
import pyautogui


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def click(x=None, y=None):

    pyautogui.click(x=x, y=y)

    return "Clicked."


def left(x=None, y=None):

    pyautogui.click(x=x, y=y, button="left")

    return "Left click completed."


def right(x=None, y=None):

    pyautogui.click(x=x, y=y, button="right")

    return "Right click completed."


def middle(x=None, y=None):

    pyautogui.click(x=x, y=y, button="middle")

    return "Middle click completed."


def double(x=None, y=None):

    pyautogui.doubleClick(x=x, y=y)

    return "Double click completed."


def triple(x=None, y=None):

    pyautogui.tripleClick(x=x, y=y)

    return "Triple click completed."


def click_after_delay(delay, x=None, y=None):

    time.sleep(delay)

    pyautogui.click(x=x, y=y)

    return f"Clicked after {delay} second(s)."


def multiple(count, interval=0.1, x=None, y=None):

    for _ in range(count):

        pyautogui.click(x=x, y=y)

        time.sleep(interval)

    return f"Clicked {count} time(s)."


def hold(button="left", duration=1):

    pyautogui.mouseDown(button=button)

    time.sleep(duration)

    pyautogui.mouseUp(button=button)

    return f"Held {button} button for {duration} second(s)."


def click_image(image_path, confidence=0.9):

    location = pyautogui.locateCenterOnScreen(
        image_path,
        confidence=confidence
    )

    if location is None:

        return "Image not found."

    pyautogui.click(location)

    return f"Clicked image at {location}."


def safe_click(image_path, confidence=0.9):

    try:

        return click_image(image_path, confidence)

    except Exception as e:

        return f"Error: {e}"