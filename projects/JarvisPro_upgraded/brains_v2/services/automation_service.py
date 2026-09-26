from brains_v2.automation_manager import automation_manager


class AutomationService:
    """Pipeline stage that hands a command to the automation manager.

    BUG FIX: this module used to do ``from brains_v2.automation_manager
    import process``. No such name exists -- automation_manager.py only
    defines ``AutomationManager`` and the ``automation_manager`` singleton.
    The bad import raised at module level, which killed the whole
    ``brains_v2.core`` package (8 modules) because core/__init__.py imports
    this file.
    """

    def process(self, data):
        command = data.get("command") if isinstance(data, dict) else data

        if not command:
            return data

        try:
            result = automation_manager.execute(command)
        except Exception as error:
            return {"reply": "Automation failed: %s" % error}

        if result:
            return {"reply": result} if isinstance(result, str) else result

        return data


automation_service = AutomationService()
