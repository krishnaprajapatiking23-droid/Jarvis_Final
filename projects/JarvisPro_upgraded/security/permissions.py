from conversation.identity import identity

OWNER = identity.owner()


def is_owner(name):
    """True when ``name`` matches the configured owner."""

    expected = identity.owner() or OWNER

    if not expected:
        return False

    return str(name).strip().casefold() == str(expected).strip().casefold()


def has_system_access(name):

    return is_owner(name)