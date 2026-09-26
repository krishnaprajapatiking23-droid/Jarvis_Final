"""
Volume Control
Jarvis Pro
"""

from ctypes import POINTER, cast

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    class Volume:

        def __init__(self):
            try:
                devices = AudioUtilities.GetSpeakers()

                interface = devices.Activate(
                    IAudioEndpointVolume._iid_,
                    CLSCTX_ALL,
                    None
                )

                self.volume = cast(
                    interface,
                    POINTER(IAudioEndpointVolume)
                )

                self.available = True

            except Exception as e:
                print(f"[Volume] Disabled: {e}")
                self.available = False

        def _check(self):
            if not self.available:
                return {
                    "success": False,
                    "message": "Volume control unavailable."
                }
            return None

        def mute(self):
            error = self._check()
            if error:
                return error

            self.volume.SetMute(1, None)
            return {"success": True, "message": "Muted."}

        def unmute(self):
            error = self._check()
            if error:
                return error

            self.volume.SetMute(0, None)
            return {"success": True, "message": "Unmuted."}

        def set_volume(self, percent):
            error = self._check()
            if error:
                return error

            percent = max(0, min(100, int(percent)))
            level = -65 + (percent / 100) * 65
            self.volume.SetMasterVolumeLevel(level, None)

            return {
                "success": True,
                "message": f"Volume set to {percent}%."
            }

        def increase(self, step=10):
            error = self._check()
            if error:
                return error

            return self.set_volume(self.get_volume() + step)

        def decrease(self, step=10):
            error = self._check()
            if error:
                return error

            return self.set_volume(self.get_volume() - step)

        def get_volume(self):
            error = self._check()
            if error:
                return 0

            level = self.volume.GetMasterVolumeLevel()
            percent = int((level + 65) / 65 * 100)
            return max(0, min(100, percent))

except Exception as e:

    print(f"[Volume] Module disabled: {e}")

    class Volume:

        def __init__(self):
            self.available = False

        def __getattr__(self, name):
            def dummy(*args, **kwargs):
                return {
                    "success": False,
                    "message": "Volume control unavailable."
                }
            return dummy

volume = Volume()