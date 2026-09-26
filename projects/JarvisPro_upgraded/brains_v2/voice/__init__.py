"""
Voice package.

Members are resolved lazily (PEP 562) so that importing one part of the
voice layer - for example ``brains_v2.voice.speaker`` - no longer pulls
in the microphone, the wake word engine and the whole brain pipeline.
``from brains_v2.voice import speaker`` keeps working exactly as before.
"""

from importlib import import_module

_MEMBERS = {
    "microphone": (".microphone", "microphone"),
    "speaker": (".speaker", "speaker"),
    "wakeword": (".wakeword", "wakeword"),
    "listener": (".listener", "listener"),
    "pipeline": (".pipeline", "pipeline"),
}

__all__ = list(_MEMBERS)


def __getattr__(name):
    try:
        module_name, attribute = _MEMBERS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(list(globals()) + __all__))
