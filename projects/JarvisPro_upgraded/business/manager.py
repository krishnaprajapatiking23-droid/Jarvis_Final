from business.product_research import research_product
from business.meta_ads import create_meta_ads
from business.product_description import create_description
from business.pricing import calculate_price
from business.profit import calculate_profit
from business.audience import find_audience
from business.strategy import business_strategy
from business.competitors import competitor_analysis

def business_manager(command):

    text = command.lower()

    if any(word in text for word in [
    "product",
    "research",
    "winning",
    "shopify",
    "sell"
    ]):
        return research_product(command)
    if "meta" in text or "facebook" in text or "ad" in text:
        return create_meta_ads(command)

    if "description" in text:
        return create_description(command)

    if "price" in text:
        return calculate_price(command)

    if "profit" in text:
        return calculate_profit(command)

    if "audience" in text:
        return find_audience(command)

    if "strategy" in text:
        return business_strategy(command)

    if "competitor" in text:
        return competitor_analysis(command)

    return None