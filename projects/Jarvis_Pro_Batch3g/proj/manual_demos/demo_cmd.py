import subprocess
import time

print("Before")

subprocess.Popen(
    ["cmd.exe"],
    creationflags=subprocess.CREATE_NEW_CONSOLE
)

print("After")

time.sleep(10)