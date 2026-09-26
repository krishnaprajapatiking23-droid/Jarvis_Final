from emotion.detector import detect_emotion
from emotion.satisfaction import (
    is_unsatisfied,
    clarification_questions
)
from emotion.response_style import style_answer

from ai.manager import ask


def conversation_manager(user, username):

    # Detect emotion
    emotion = detect_emotion(user)

    print("\n========== CONVERSATION ==========")
    print("Emotion :", emotion)
    print("==================================")

    # Check satisfaction
    if is_unsatisfied(user):

        questions = clarification_questions()

        message = (
            "I'm sorry my previous answer wasn't helpful.\n\n"
            "Let me understand your needs better.\n\n"
        )

        for question in questions:

            message += f"• {question}\n"

        return message

    # AI Response
    messages = [
        {
            "role": "user",
            "content": user
        }
    ]

    answer = ask(user, messages)

    # Apply response style
    answer = style_answer(answer, emotion)

    return answer