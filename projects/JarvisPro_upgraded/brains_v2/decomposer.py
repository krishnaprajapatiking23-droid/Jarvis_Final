class GoalDecomposer:

    def decompose(self, command):

        command = command.strip().lower()

        if "jarvis" in command or "ai assistant" in command:

            return [
                "Analyze requirements",
                "Design architecture",
                "Create Brain",
                "Create Memory",
                "Create Voice",
                "Create Interface",
                "Integrate components",
                "Test system",
                "Verify output",
            ]

        if "website" in command or "web app" in command:

            return [
                "Analyze requirements",
                "Plan website structure",
                "Design UI",
                "Build Frontend",
                "Build Backend",
                "Integrate functionality",
                "Test website",
                "Verify responsive layout",
                "Deploy",
            ]

        if "mobile app" in command or "android app" in command:

            return [
                "Analyze requirements",
                "Plan application architecture",
                "Design mobile UI",
                "Build application",
                "Implement functionality",
                "Test on target device",
                "Fix issues",
                "Verify final application",
            ]

        if "shopping app" in command or "ecommerce" in command:

            return [
                "Analyze requirements",
                "Design product catalog",
                "Design shopping interface",
                "Implement product system",
                "Implement cart and checkout",
                "Integrate required services",
                "Test purchase flow",
                "Verify application",
            ]

        if "chatbot" in command or "chat bot" in command:

            return [
                "Analyze requirements",
                "Design conversation flow",
                "Configure AI model",
                "Build chatbot interface",
                "Implement message processing",
                "Test conversations",
                "Fix issues",
                "Verify chatbot",
            ]

        if "python" in command and (
            "application" in command
            or "app" in command
            or "program" in command
        ):

            return [
                "Analyze requirements",
                "Design application structure",
                "Implement Python code",
                "Add required functionality",
                "Run tests",
                "Fix issues",
                "Verify application",
            ]

        if "organize" in command and (
            "file" in command
            or "folder" in command
            or "project" in command
        ):

            return [
                "Inspect existing files",
                "Identify file categories",
                "Plan folder structure",
                "Organize files",
                "Check references",
                "Verify organization",
            ]

        return [
            "Analyze",
            "Plan",
            "Execute",
            "Test",
            "Verify",
        ]


decomposer = GoalDecomposer()