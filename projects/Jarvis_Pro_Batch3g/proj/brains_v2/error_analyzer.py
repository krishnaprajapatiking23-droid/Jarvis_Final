import traceback
from collections import Counter


class ErrorAnalyzer:

    def __init__(self):

        self.error_history = []

    def classify(self, error):

        text = str(error).lower()

        if isinstance(error, FileNotFoundError):
            return "File"

        if isinstance(error, PermissionError):
            return "Permission"

        if isinstance(error, TimeoutError):
            return "Timeout"

        if isinstance(error, ConnectionError):
            return "Network"

        if isinstance(error, MemoryError):
            return "Memory"

        if isinstance(error, KeyboardInterrupt):
            return "Interrupted"

        if "module" in text or "import" in text:
            return "Import"

        if "attribute" in text:
            return "Attribute"

        if "type" in text:
            return "Type"

        if "value" in text:
            return "Value"

        if "key" in text:
            return "Key"

        if "index" in text:
            return "Index"

        return "Unknown"

    def suggestion(self, category):

        suggestions = {

            "File":
                "Check whether the file exists and the path is correct.",

            "Permission":
                "Verify file or folder permissions.",

            "Timeout":
                "Retry the operation or increase the timeout.",

            "Network":
                "Check the internet connection or API availability.",

            "Memory":
                "Reduce memory usage or optimize processing.",

            "Import":
                "Install the missing package or verify imports.",

            "Attribute":
                "Check object names and available methods.",

            "Type":
                "Verify argument and variable types.",

            "Value":
                "Validate input values before processing.",

            "Key":
                "Check dictionary keys before accessing them.",

            "Index":
                "Ensure list indexes are within range.",

            "Interrupted":
                "Operation stopped by the user.",

            "Unknown":
                "Inspect the traceback for more details."
        }

        return suggestions.get(category, suggestions["Unknown"])

    def analyze(self, error):

        category = self.classify(error)

        report = {

            "category": category,

            "error": str(error),

            "suggestion": self.suggestion(category),

            "traceback": traceback.format_exc()

        }

        self.error_history.append(report)

        return report

    def history(self):

        return self.error_history

    def statistics(self):

        counter = Counter()

        for item in self.error_history:

            counter[item["category"]] += 1

        return dict(counter)

    # ============================================
    # Complete Report
    # ============================================

    def report(self):

        return {

            "total_errors": len(self.error_history),

            "statistics": self.statistics(),

            "recent_errors": self.error_history[-10:]

        }

    def clear(self):

        self.error_history.clear()

        return True


error_analyzer = ErrorAnalyzer()