from automation import (
    desktop,
    system_info,
    clipboard,
    processes,
)

print("=" * 60)
print("SPRINT A1 TEST")
print("=" * 60)

print(system_info.summary())

clipboard.copy("Jarvis Sprint A1")

print(clipboard.paste())

print(processes.is_running("explorer"))

desktop.open_desktop()

print()

print("SPRINT A1 PASSED")