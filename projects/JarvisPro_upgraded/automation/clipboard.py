"""Clipboard manager with explicit unavailable-state handling."""
import logging
log = logging.getLogger("jarvis.clipboard")


def _backend():
    try:
        import pyperclip
        return pyperclip
    except ImportError:
        return None


class Clipboard:
    def available(self):
        return _backend() is not None

    def copy(self, text):
        backend = _backend()
        if backend is None:
            return {"success": False, "message": "Clipboard backend unavailable: install pyperclip."}
        try:
            backend.copy(str(text))
            return {"success": True, "message": "Copied."}
        except Exception as error:
            log.exception("clipboard copy failed")
            return {"success": False, "message": f"Clipboard failure: {error}"}

    def paste(self):
        backend = _backend()
        if backend is None:
            return ""
        try:
            return backend.paste()
        except Exception as error:
            log.exception("clipboard paste failed")
            return ""

    def clear(self):
        return self.copy("")

    def execute(self, command):
        text = str(command or "").lower()
        if "clear" in text:
            return self.clear()
        if "paste" in text:
            return {"success": True, "data": self.paste(), "message": "Clipboard read."}
        return {"success": False, "message": "Specify copy, paste, or clear."}


clipboard = Clipboard()


# BUG FIX: callers used module-level helpers (``clipboard.copy``,
# ``copy_text``) that did not exist -- demo_sprint_a1 raised
# AttributeError: module 'automation.clipboard' has no attribute 'copy' and
# demo_clipboard raised NameError: name 'copy_text' is not defined. These
# thin wrappers expose the singleton's methods at module level.


def copy(text):
    """Put ``text`` on the clipboard."""
    return clipboard.copy(text)


def paste():
    """Read the clipboard, or "" when no backend is installed."""
    return clipboard.paste()


def clear():
    """Empty the clipboard."""
    return clipboard.clear()


def available():
    """True when a clipboard backend is installed."""
    return clipboard.available()


# Legacy names.
copy_text = copy
paste_text = paste
