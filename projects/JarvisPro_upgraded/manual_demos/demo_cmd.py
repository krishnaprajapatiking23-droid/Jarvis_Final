# BUG FIX: subprocess.CREATE_NEW_CONSOLE only exists on Windows, so
# this module raised AttributeError on Linux and macOS.
import subprocess
import time

print("Before")

subprocess.Popen(
    ["cmd.exe"],
    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
)

print("After")

time.sleep(10)