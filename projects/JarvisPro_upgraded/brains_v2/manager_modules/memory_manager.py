from memory.memory_engine import process_memory


def process(command):

    result = process_memory(command)

    if result:
        return {
            "reply": result
        }

    return None