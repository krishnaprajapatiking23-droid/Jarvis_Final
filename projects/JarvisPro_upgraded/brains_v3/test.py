from brains_v3.intent_engine import intent_engine

while True:

    cmd = input("You : ")

    result = intent_engine.detect(cmd)

    print(result)