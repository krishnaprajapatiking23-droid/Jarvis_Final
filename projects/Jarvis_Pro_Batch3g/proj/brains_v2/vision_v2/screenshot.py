def capture(path='vision_screen.png'):
 try:import pyautogui
 except ImportError:return {'success':False,'error':'screenshot backend unavailable'}
 try:pyautogui.screenshot().save(path);return path
 except Exception as e:return {'success':False,'error':f'screenshot failure: {e}'}
