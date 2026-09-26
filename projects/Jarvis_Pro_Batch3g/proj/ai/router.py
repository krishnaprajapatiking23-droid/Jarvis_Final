def detect_agent(command):

    text = command.lower()

    # Coding
    if any(word in text for word in [
        "python",
        "code",
        "program",
        "bug",
        "error",
        "debug",
        "flask",
        "django",
        "html",
        "css",
        "javascript"
    ]):
        return "coding"

    # Business
    if any(word in text for word in [
        "shopify",
        "dropshipping",
        "meta",
        "facebook",
        "ads",
        "marketing",
        "product",
        "roas",
        "ecommerce",
        "business"
    ]):
        return "business"

    # Study
    if any(word in text for word in [
        "study",
        "physics",
        "chemistry",
        "math",
        "biology",
        "exam",
        "chapter"
    ]):
        return "study"

    # Vision
    if any(word in text for word in [
        "image",
        "photo",
        "picture",
        "screen",
        "screenshot",
        "vision"
    ]):
        return "vision"

    # Creative
    if any(word in text for word in [
        "edit",
        "video",
        "thumbnail",
        "banner",
        "logo",
        "poster",
        "design"
    ]):
        return "creative"

    return "chat"