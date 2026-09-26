from brains_v2.automation_manager import process

class AutomationService:

    def process(self, data):

        result = process(data["command"])

        if result:

            return result

        return data


automation_service = AutomationService()