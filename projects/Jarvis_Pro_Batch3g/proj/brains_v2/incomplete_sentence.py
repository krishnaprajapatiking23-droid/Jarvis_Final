class IncompleteSentenceEngine:

    ACTION_WORDS = {
        "open",
        "close",
        "create",
        "delete",
        "make",
        "fix",
        "run",
        "start",
        "stop",
        "show",
        "play",
        "go",
        "send",
        "write",
    }

    def analyze(self, command):
        text = str(command).strip()

        if not text:
            return {
                "incomplete": True,
                "reason": "empty_input",
                "completion_needed": True,
            }

        if text.endswith("..."):
            return {
                "incomplete": True,
                "reason": "trailing_ellipsis",
                "completion_needed": True,
            }

        words = text.lower().split()

        if len(words) >= 2 and words[0] in self.ACTION_WORDS:
            if words[-1] in {
                "the",
                "a",
                "an",
            }:
                return {
                    "incomplete": True,
                    "reason": "missing_object",
                    "completion_needed": True,
                }

        if len(words) >= 2 and words[-1] in {
            "a",
            "an",
            "the",
            "to",
            "with",
            "for",
            "from",
            "of",
            "in",
            "on",
        }:
            return {
                "incomplete": True,
                "reason": "unfinished_phrase",
                "completion_needed": True,
            }

        return {
            "incomplete": False,
            "reason": None,
            "completion_needed": False,
        }


incomplete_sentence = IncompleteSentenceEngine()