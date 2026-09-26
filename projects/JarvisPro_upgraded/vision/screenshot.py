from pathlib import Path
SAVE_PATH=Path('vision/screenshots')

def take_screenshot():
    """Take a screenshot and return the file path.
    
    Returns a string path on success.
    On failure (no pyautogui, no display) returns None so callers can
    handle the missing screenshot gracefully without type errors.
    """
    try:
        import pyautogui
    except ImportError:
        return None
    try:
        SAVE_PATH.mkdir(parents=True, exist_ok=True)
        path = SAVE_PATH / 'screen.png'
        pyautogui.screenshot().save(path)
        return str(path)
    except Exception:
        return None
