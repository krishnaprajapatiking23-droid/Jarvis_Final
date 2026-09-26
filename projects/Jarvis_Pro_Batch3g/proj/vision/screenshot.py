from pathlib import Path
SAVE_PATH=Path('vision/screenshots')
def take_screenshot():
 try:import pyautogui
 except ImportError:return {'success':False,'error':'screenshot backend unavailable'}
 try:
  SAVE_PATH.mkdir(parents=True,exist_ok=True);path=SAVE_PATH/'screen.png';pyautogui.screenshot().save(path);return str(path)
 except Exception as e:return {'success':False,'error':f'screenshot failure: {e}'}
