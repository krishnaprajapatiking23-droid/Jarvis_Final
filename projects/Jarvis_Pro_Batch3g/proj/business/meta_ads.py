from business.ai import ask_business


def create_meta_ads(command):

    prompt = f"""
You are an expert Meta Ads copywriter.

Create high-converting Meta Ads for:

{command}

Generate:

1. Primary Text
2. Headline
3. Description
4. CTA
5. Hook
6. Creative Idea
"""

    return ask_business(prompt)