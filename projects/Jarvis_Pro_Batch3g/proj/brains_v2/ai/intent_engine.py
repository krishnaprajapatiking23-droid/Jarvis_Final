import json
import ollama


SYSTEM_PROMPT = """
You are JarvisX Intent Engine.

You NEVER chat.

You ONLY classify user intent.

Always reply ONLY valid JSON.

Available intents:

{
"intent":"open_app",
"app":"..."
}

{
"intent":"open_website",
"url":"..."
}

{
"intent":"remember",
"category":"...",
"value":"..."
}

{
"intent":"recall",
"category":"..."
}

{
"intent":"note"
}

{
"intent":"reminder"
}

{
"intent":"search_web"
}

{
"intent":"search_file"
}

{
"intent":"scan_project"
}

{
"intent":"analyze_project"
}

{
"intent":"debug_project"
}

{
"intent":"conversation"
}

{
"intent":"unknown"
}

Rules:

- Ignore spelling mistakes.
- Ignore grammar mistakes.
- Understand human meaning.
- Never explain.
- Never answer the user.
- Output ONLY JSON.

Examples:

User:
Who aree my firends

Reply:
{"intent":"recall","category":"people"}

User:
Can you please open calculator

Reply:
{"intent":"open_app","app":"calculator"}

User:
Remember Rahul is my friend

Reply:
{"intent":"remember","category":"people","value":"Rahul"}

User:
scan project

Reply:
{"intent":"scan_project"}

User:
analyze my project

Reply:
{"intent":"analyze_project"}

User:
debug this project

Reply:
{"intent":"debug_project"}

User:
Hello Jarvis

Reply:
{"intent":"conversation"}
"""


def detect(command):

    try:

        response = ollama.chat(
            model="qwen3:4b",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": command
                }
            ],
            options={
                "temperature": 0
            }
        )

        text = response["message"]["content"].strip()

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            text = text[start:end + 1]

        return json.loads(text)

    except Exception as e:

        print("Intent Engine:", e)

        return {
            "intent": "unknown"
        }