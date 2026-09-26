import webbrowser

WEBSITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "chatgpt": "https://chat.openai.com",
    "gmail": "https://mail.google.com",
    "shopify": "https://www.shopify.com",
    "whatsapp": "https://web.whatsapp.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com",
}

def open_website(command):

    command = command.lower().strip()

    for site, url in WEBSITES.items():

        if site in command:

            webbrowser.open(url)

            return f"Opening {site.title()}."

    return None