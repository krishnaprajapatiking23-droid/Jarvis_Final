import pyautogui


def move(x, y):

    pyautogui.moveTo(x, y, duration=0.3)


def click():

    pyautogui.click()


def right_click():

    pyautogui.rightClick()