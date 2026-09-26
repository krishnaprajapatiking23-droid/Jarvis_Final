"""
Conversation States
"""

STANDBY = "standby"
ACTIVE = False
SLEEP = "sleep"
STATE_ACTIVE = "active"


def wake():
    global ACTIVE
    ACTIVE = True
    return ACTIVE


def sleep():
    global ACTIVE
    ACTIVE = False
    return ACTIVE


def is_active():
    return ACTIVE