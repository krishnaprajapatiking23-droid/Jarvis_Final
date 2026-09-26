from intelligence.classifier import classify_request


def intelligence_manager(command):

    request = classify_request(command)

    print("\n========== AI INTELLIGENCE ==========")
    print("Category :", request)
    print("=====================================")

    return request