"""
Memory Utilities
"""

import re


def clean(text):

    return re.sub(

        r"\s+",

        " ",

        text.strip()

    )


def normalize(text):

    return clean(text).lower()