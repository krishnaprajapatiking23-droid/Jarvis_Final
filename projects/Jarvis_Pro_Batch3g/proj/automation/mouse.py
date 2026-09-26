import time
import pyautogui


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def position():

    return pyautogui.position()


def move(x, y, duration=0.3):

    pyautogui.moveTo(x, y, duration=duration)

    return f"Mouse moved to ({x}, {y})"


def move_relative(dx, dy, duration=0.3):

    pyautogui.moveRel(dx, dy, duration=duration)

    return f"Mouse moved by ({dx}, {dy})"


def left_click(x=None, y=None):

    pyautogui.click(x=x, y=y)

    return "Left click performed."


def right_click(x=None, y=None):

    pyautogui.rightClick(x=x, y=y)

    return "Right click performed."


def middle_click(x=None, y=None):

    pyautogui.middleClick(x=x, y=y)

    return "Middle click performed."


def double_click(x=None, y=None):

    pyautogui.doubleClick(x=x, y=y)

    return "Double click performed."


def triple_click(x=None, y=None):

    pyautogui.tripleClick(x=x, y=y)

    return "Triple click performed."


def drag(start_x, start_y, end_x, end_y, duration=0.5):

    pyautogui.moveTo(start_x, start_y)

    pyautogui.dragTo(end_x, end_y, duration=duration)

    return "Drag completed."


def drag_relative(dx, dy, duration=0.5):

    pyautogui.dragRel(dx, dy, duration=duration)

    return "Relative drag completed."


def scroll_up(amount=500):

    pyautogui.scroll(amount)

    return "Scrolled up."


def scroll_down(amount=500):

    pyautogui.scroll(-amount)

    return "Scrolled down."


def mouse_down(button="left"):

    pyautogui.mouseDown(button=button)

    return f"{button.capitalize()} button pressed."


def mouse_up(button="left"):

    pyautogui.mouseUp(button=button)

    return f"{button.capitalize()} button released."


def hover(x, y, seconds=2):

    pyautogui.moveTo(x, y)

    time.sleep(seconds)

    return f"Hovered for {seconds} second(s)."


def screen_size():

    return pyautogui.size()