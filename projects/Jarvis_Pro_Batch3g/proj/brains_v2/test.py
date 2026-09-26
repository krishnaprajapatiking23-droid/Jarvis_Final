from psychology.coach import PersonalCoach

coach = PersonalCoach()

tests = [

    "I am very happy today",

    "I failed my exam",

    "I hate everything",

    "I am nervous about tomorrow",

    "I am ready to win"

]

for text in tests:

    print("=" * 70)

    print("INPUT:")
    print(text)

    result = coach.coach(text)

    print("\nRESULT:")
    print(result)