"""
Sample JARVIS plugin.

Copy this file to build your own: keep the ``PLUGIN`` dict and the ``run``
function, drop it in ``plugins/`` and call ``plugins.reload()`` - no restart
and no changes anywhere else in the project.
"""

from __future__ import annotations


PLUGIN = {
    "name": "hello_jarvis",
    "description": "Sample plugin that greets someone by name.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {
                "type": "STRING",
                "description": "Who to greet.",
            }
        },
        "required": [],
    },
}


def run(name: str = "sir", **_: object) -> str:
    return f"Hello {name}, the plugin system is working."
