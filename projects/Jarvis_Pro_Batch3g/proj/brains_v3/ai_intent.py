from brains_v2.llm.provider import LLMProvider

import sys
import os
import httpx

try:
    from ollama import Client
except ImportError:
    Client = None


print("PYTHON:", sys.executable)
print("HTTPX:", httpx.__version__)
print("HTTP_PROXY:", os.environ.get("HTTP_PROXY"))
print("HTTPS_PROXY:", os.environ.get("HTTPS_PROXY"))
print("NO_PROXY:", os.environ.get("NO_PROXY"))


class OllamaProvider(LLMProvider):

    name = "Ollama"
    model = "qwen3:4b"

    def __init__(self):

        self.client = None

        if Client is None:
            print("❌ Ollama Python package not installed.")
            return

        try:
            self.client = Client(
                host="http://127.0.0.1:11434"
            )

            # Test server connection
            self.client.list()

            print("✅ Ollama Connected")

        except Exception as e:

            print("❌ Ollama Connection Failed")
            print("Reason:", repr(e))

            self.client = None

    def available(self):

        return self.client is not None

    def generate(self, prompt):

        if not self.available():
            return "Ollama is offline."

        try:

            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            if not response:
                return "No response received from Ollama."

            if "message" not in response:
                return "Invalid response from Ollama."

            return response["message"]["content"]

        except Exception as e:

            print("\n========== OLLAMA ERROR ==========")
            print(type(e).__name__)
            print(repr(e))
            print("==================================\n")

            # Try reconnecting once
            try:
                self.client = Client(
                    host="http://127.0.0.1:11434"
                )

                self.client.list()

                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                return response["message"]["content"]

            except Exception as reconnect_error:

                print("Reconnect Failed:")
                print(repr(reconnect_error))

                self.client = None

                return "Ollama is offline."