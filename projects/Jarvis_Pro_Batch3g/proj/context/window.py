"""Active-window lookup with optional backend handling."""

def active_window():
    try:
        import pygetwindow as gw
    except ImportError:
        return ""
    try:
        window = gw.getActiveWindow()
        return str(getattr(window, "title", "") or "")
    except Exception:
        return ""
