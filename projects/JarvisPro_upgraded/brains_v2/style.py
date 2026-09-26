class StyleEngine:

    def __init__(self):

        self.style = "friendly"

    def update(self, personality):

        mode = personality["mode"]

        if mode == "professional":

            self.style = "professional"

        elif mode == "analytical":

            self.style = "analytical"

        else:

            self.style = "friendly"

    def apply(self, text):
        """Return the reply unchanged.

        Style used to be expressed by prepending a fixed phrase to every
        reply ("Certainly. ", "After analyzing the situation, "), which is
        one of the main reasons JARVIS sounded like a template.  Tone is
        now carried by the per-turn generation directives in
        conversation/style_controller.py.  The method is kept so existing
        callers (brains_v2/manager.py, reply_controller) keep working.
        """

        return text

    def current(self):

        return self.style


style = StyleEngine()