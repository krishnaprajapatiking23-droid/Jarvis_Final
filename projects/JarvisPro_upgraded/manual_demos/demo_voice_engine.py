from voice.voice_engine import listen_and_speak
from core.router import route_command

username = "Krishna"

while True:

    command = listen_and_speak()

    if not command:
        continue

    if command.lower() == "exit":
        break

    answer = route_command(command, username)

    print("\nJarvis:", answer)