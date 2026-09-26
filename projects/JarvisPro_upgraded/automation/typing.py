import time
import random
import pyautogui


pyautogui.FAILSAFE = True


def type_text(text, interval=0.02):

    pyautogui.write(text, interval=interval)

    return "Typing completed."


def type_human(text, min_delay=0.03, max_delay=0.12):

    for char in text:

        pyautogui.write(char)

        time.sleep(random.uniform(min_delay, max_delay))

    return "Human-like typing completed."


def type_line(text):

    pyautogui.write(text, interval=0.02)

    pyautogui.press("enter")

    return "Line typed."


def type_lines(lines):

    for line in lines:

        pyautogui.write(str(line), interval=0.02)

        pyautogui.press("enter")

    return "Lines typed."


def type_file(path):

    try:

        with open(path, "r", encoding="utf-8") as file:

            content = file.read()

        pyautogui.write(content, interval=0.02)

        return "File typed successfully."

    except Exception as e:

        return f"Error: {e}"


def countdown(seconds=3):

    for i in range(seconds, 0, -1):

        print(f"Typing starts in {i}...")

        time.sleep(1)

    return "Countdown completed."


def type_after_delay(text, delay=3):

    time.sleep(delay)

    pyautogui.write(text, interval=0.02)

    return "Typing completed after delay."


def press_enter():

    pyautogui.press("enter")

    return "Pressed Enter."


def clear_line():

    pyautogui.hotkey("shift", "home")

    pyautogui.press("backspace")

    return "Current line cleared."


def repeat(text, count=1):

    for _ in range(count):

        pyautogui.write(text, interval=0.02)

    return f"Repeated {count} time(s)."


def paragraph(text):

    pyautogui.write(text, interval=0.02)

    pyautogui.press("enter")
    pyautogui.press("enter")

    return "Paragraph typed."