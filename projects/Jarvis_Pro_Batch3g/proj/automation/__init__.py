"""Automation package with lazy optional desktop backends."""
__all__ = ["desktop", "power", "screenshots", "volume", "clipboard", "processes", "windows", "system_info"]

def __getattr__(name):
    import importlib
    mapping = {
        "desktop": (".desktop", "desktop"), "power": (".power", "power"),
        "screenshots": (".screenshots", "screenshots"), "volume": (".volume", "volume"),
        "clipboard": (".clipboard", "clipboard"), "processes": (".process", "processes"),
        "windows": (".window_manager", "windows"), "system_info": (".system_info", "system_info"),
    }
    if name not in mapping:
        raise AttributeError(name)
    module, attribute = mapping[name]
    return getattr(importlib.import_module(module, __name__), attribute)
