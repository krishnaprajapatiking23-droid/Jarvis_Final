import time
import pyautogui


pyautogui.FAILSAFE = True


def press(key):

    pyautogui.press(key)

    return f"Pressed '{key}'"


def hold(key):

    pyautogui.keyDown(key)

    return f"Holding '{key}'"


def release(key):

    pyautogui.keyUp(key)

    return f"Released '{key}'"


def hotkey(*keys):

    pyautogui.hotkey(*keys)

    return f"Pressed {' + '.join(keys)}"


def write(text, interval=0.02):

    pyautogui.write(text, interval=interval)

    return "Typing completed."


def type_slow(text, interval=0.10):

    pyautogui.write(text, interval=interval)

    return "Slow typing completed."


def enter():

    pyautogui.press("enter")

    return "Pressed Enter."


def backspace(count=1):

    for _ in range(count):

        pyautogui.press("backspace")

    return f"Pressed Backspace {count} time(s)."


def delete(count=1):

    for _ in range(count):

        pyautogui.press("delete")

    return f"Pressed Delete {count} time(s)."


def tab(count=1):

    for _ in range(count):

        pyautogui.press("tab")

    return f"Pressed Tab {count} time(s)."


def space(count=1):

    for _ in range(count):

        pyautogui.press("space")

    return f"Pressed Space {count} time(s)."


def esc():

    pyautogui.press("esc")

    return "Pressed Escape."


def select_all():

    pyautogui.hotkey("ctrl", "a")

    return "Selected all."


def copy():

    pyautogui.hotkey("ctrl", "c")

    return "Copied."


def cut():

    pyautogui.hotkey("ctrl", "x")

    return "Cut."


def paste():

    pyautogui.hotkey("ctrl", "v")

    return "Pasted."


def undo():

    pyautogui.hotkey("ctrl", "z")

    return "Undo."


def redo():

    pyautogui.hotkey("ctrl", "y")

    return "Redo."


def save():

    pyautogui.hotkey("ctrl", "s")

    return "Saved."


def wait(seconds):

    time.sleep(seconds)

    return f"Waited {seconds} second(s)."