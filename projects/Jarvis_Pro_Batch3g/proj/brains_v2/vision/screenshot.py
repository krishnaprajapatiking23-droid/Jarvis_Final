from pathlib import Path

def capture(path="screen.png"):
    try:
        import pyautogui
    except ImportError:
        return {"success": False, "error": "screenshot backend unavailable"}
    try:
        image = pyautogui.screenshot()
        image.save(path)
        return str(Path(path))
    except Exception as error:
        return {"success": False, "error": f"screenshot failure: {error}"}
