import pyautogui


def desktop():
    pyautogui.hotkey("win", "d")
    return "Desktop opened."


def run():
    pyautogui.hotkey("win", "r")
    return "Run dialog opened."


def explorer():
    pyautogui.hotkey("win", "e")
    return "File Explorer opened."


def settings():
    pyautogui.hotkey("win", "i")
    return "Windows Settings opened."


def search():
    pyautogui.hotkey("win", "s")
    return "Windows Search opened."


def task_manager():
    pyautogui.hotkey("ctrl", "shift", "esc")
    return "Task Manager opened."


def lock():
    pyautogui.hotkey("win", "l")
    return "Computer locked."


def minimize_all():
    pyautogui.hotkey("win", "m")
    return "All windows minimized."


def maximize_window():
    pyautogui.hotkey("win", "up")
    return "Window maximized."


def minimize_window():
    pyautogui.hotkey("win", "down")
    return "Window minimized."


def close_window():
    pyautogui.hotkey("alt", "f4")
    return "Window closed."


def switch_window():
    pyautogui.hotkey("alt", "tab")
    return "Switched window."


def new_tab():
    pyautogui.hotkey("ctrl", "t")
    return "New tab opened."


def close_tab():
    pyautogui.hotkey("ctrl", "w")
    return "Tab closed."


def reopen_tab():
    pyautogui.hotkey("ctrl", "shift", "t")
    return "Last closed tab reopened."


def next_tab():
    pyautogui.hotkey("ctrl", "tab")
    return "Next tab."


def previous_tab():
    pyautogui.hotkey("ctrl", "shift", "tab")
    return "Previous tab."


def refresh():
    pyautogui.press("f5")
    return "Refreshed."


def screenshot():
    pyautogui.hotkey("win", "shift", "s")
    return "Screenshot tool opened."


def emoji():
    pyautogui.hotkey("win", ".")
    return "Emoji panel opened."


def clipboard():
    pyautogui.hotkey("win", "v")
    return "Clipboard history opened."


def action_center():
    pyautogui.hotkey("win", "a")
    return "Action Center opened."