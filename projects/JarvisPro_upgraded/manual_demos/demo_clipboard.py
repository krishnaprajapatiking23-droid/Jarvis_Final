from automation.clipboard import *
import time

print("Switch to Notepad...")

time.sleep(5)

copy_text("Hello Krishna!")

time.sleep(1)

paste()