"""
Screenshot Engine
Jarvis Version 2
"""

from pathlib import Path
from datetime import datetime
import pyautogui


class ScreenshotManager:

    def __init__(self):

        self.folder = Path("screenshots")

        self.folder.mkdir(exist_ok=True)

    def capture(self):

        filename = datetime.now().strftime(
            "%Y%m%d_%H%M%S.png"
        )

        filepath = self.folder / filename

        image = pyautogui.screenshot()

        image.save(filepath)

        return {

            "success": True,

            "path": str(filepath),

            "message": "Screenshot captured."

        }

    def capture_as(self, filename):

        if not filename.endswith(".png"):

            filename += ".png"

        filepath = self.folder / filename

        image = pyautogui.screenshot()

        image.save(filepath)

        return {

            "success": True,

            "path": str(filepath),

            "message": "Screenshot saved."

        }


screenshots = ScreenshotManager()