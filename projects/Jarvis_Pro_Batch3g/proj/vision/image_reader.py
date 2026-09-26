import ollama

from core.config import AI_MODEL


def describe_image(image_path):

    response = ollama.chat(

        model=AI_MODEL,

        messages=[
            {
                "role": "user",
                "content": "Describe this image in detail."
            }
        ],

        images=[image_path]

    )

    return response["message"]["content"]