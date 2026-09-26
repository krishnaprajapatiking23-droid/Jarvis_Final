from automation.apps import open_app


def test_open_app_commands():
    commands = [
        "chrome",
        "notepad",
        "calculator",
        "paint",
    ]

    for command in commands:
        result = open_app(command)

        assert result is not None