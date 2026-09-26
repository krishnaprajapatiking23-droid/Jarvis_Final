from automation.keyboard import press, write, hotkey
import time

print("Switch to Notepad in 5 seconds...")

time.sleep(5)

write("Hello Krishna!")

press("enter")

write("Jarvis Pro Keyboard Module is working.")

hotkey("ctrl", "a")