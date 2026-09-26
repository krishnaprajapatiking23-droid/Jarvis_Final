"""Target-aware window actions with optional desktop backend."""

def _driver():
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        return None


def _result(ok, message):
    return {"success": ok, "message": message}


def minimize(target=None):
    if target:
        from automation.window_manager import windows
        return _result(windows.minimize(target), f"Minimize target: {target}")
    driver = _driver()
    if driver is None: return _result(False, "Desktop automation unavailable.")
    driver.hotkey("win", "down"); return _result(True, "Window minimized.")


def maximize(target=None):
    if target:
        from automation.window_manager import windows
        return _result(windows.maximize(target), f"Maximize target: {target}")
    driver = _driver()
    if driver is None: return _result(False, "Desktop automation unavailable.")
    driver.hotkey("win", "up"); return _result(True, "Window maximized.")


def close(target=None):
    if not target: return _result(False, "Target window required; blind close refused.")
    from automation.window_manager import windows
    if not windows.focus_window(target): return _result(False, "Target window unavailable.")
    driver=_driver()
    if driver is None:return _result(False,"Desktop automation unavailable.")
    driver.hotkey("alt","f4");return _result(True,"Target window closed.")


def show_desktop():
    driver=_driver()
    if driver is None:return _result(False,"Desktop automation unavailable.")
    driver.hotkey("win","d");return _result(True,"Showing desktop.")


def switch_window(target=None):
    if not target:return _result(False,"Target window required; blind switching refused.")
    from automation.window_manager import windows
    return _result(windows.focus_window(target), f"Focus target: {target}")
