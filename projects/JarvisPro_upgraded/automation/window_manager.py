"""Window lookup with a graceful headless fallback."""

def _backend():
    try:
        import pygetwindow as gw
        return gw
    except ImportError:
        return None

class WindowManager:
    def get_windows(self):
        backend = _backend()
        return [] if backend is None else [w.title for w in backend.getAllWindows() if w.title]
    def _find(self, title):
        backend = _backend()
        if backend is None or not title:
            return None
        needle = title.lower()
        return next((w for w in backend.getAllWindows() if w.title and needle in w.title.lower()), None)
    def is_window_open(self, title): return self._find(title) is not None
    def focus_window(self, title):
        window = self._find(title)
        if window is None: return False
        try:
            if getattr(window, "isMinimized", False): window.restore()
            window.activate(); return True
        except Exception: return False
    def minimize(self, title):
        window=self._find(title)
        if not window:return False
        window.minimize();return True
    def maximize(self, title):
        window=self._find(title)
        if not window:return False
        window.maximize();return True
windows=WindowManager();is_window_open=windows.is_window_open;focus_window=windows.focus_window;minimize_window=windows.minimize;maximize_window=windows.maximize
