from brains_v2.desktop import desktop

print("Mouse will move in 3 seconds...")

import time

time.sleep(3)

desktop.move_mouse(500, 500)

desktop.click()

print("Done")