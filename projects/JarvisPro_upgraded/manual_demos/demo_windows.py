from pywinauto import Desktop

windows = Desktop(backend="uia").windows()

found = False

for window in windows:

    title = window.window_text()

    if "Notepad" in title:

        found = True

        print("Found:", title)

        try:
            window.set_focus()
            print("Notepad Activated Successfully!")

        except Exception as e:
            print("Error:", e)

        break

if not found:
    print("Notepad Not Found.")