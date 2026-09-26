def capture(path='vision_screen.png'):
    """Take a screenshot and return the file path, or None on failure."""
    try:
        import pyautogui
    except ImportError:
        return None
    try:
        pyautogui.screenshot().save(path)
        return path
    except Exception:
        return None
