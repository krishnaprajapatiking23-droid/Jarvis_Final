from automation.windows import *
import time

print("Testing in 5 seconds...")

time.sleep(5)

show_desktop()

time.sleep(2)

switch_window()

time.sleep(2)

maximize()

time.sleep(2)

minimize()