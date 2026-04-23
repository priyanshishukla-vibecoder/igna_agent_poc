BESTBUY_CATEGORIES = {
    "smartphone": "cat09000",
    "phone": "cat09000",
    "laptop": "abcat0502000",
    "tablet": "pcmcat1575399559049",
    "headphones": "abcat0204000",
    "tv": "abcat0101000",
    "camera": "abcat0400000",
    "smartwatch": "smartwatches",
}

EBAY_CATEGORIES = {
    "smartphone": "9355",
    "phone": "9355",
    "laptop": "177",
    "tablet": "171485",
    "headphones": "112529",
    "tv": "11071",
    "camera": "625",
    "smartwatch": "178893",
}


def get_product_keyword(query: str) -> str:
    return query.strip().split()[0].lower() if query.strip() else ""


def is_relevant_product_title(query: str, title: str) -> bool:
    """Keeps obviously unrelated products out of result sets."""
    keyword = get_product_keyword(query)
    normalized = title.lower()

    aliases = {
        "tablet": ["tablet", "ipad", "galaxy tab", "fire hd", "fire max", "tab "],
        "laptop": [
            "laptop",
            "notebook",
            "chromebook",
            "macbook",
            "thinkpad",
            "ideapad",
            "vivobook",
            "zenbook",
        ],
        "phone": ["phone", "smartphone", "iphone", "galaxy s", "pixel"],
        "smartphone": ["phone", "smartphone", "iphone", "galaxy s", "pixel"],
        "headphones": ["headphones", "earbuds", "airpods", "headset"],
        "tv": [" tv", "smart tv", "oled", "qled"],
        "camera": ["camera", "dslr", "mirrorless", "gopro"],
        "smartwatch": ["smartwatch", "watch", "apple watch", "galaxy watch", "fitbit"],
    }

    terms = aliases.get(keyword)
    if not terms:
        return True

    return any(term in normalized for term in terms)


def build_products(raw_items: list, site: str, max_results: int) -> list:
    """Converts raw extracted dicts into structured product records."""
    products = []
    for item in raw_items[:max_results]:
        name = item.get("title", "").replace("\n", " ").replace(
            "Opens in a new window or tab",
            "",
        ).strip()
        if not name:
            continue

        products.append(
            {
                "site": site,
                "name": name,
                "price": item.get("price"),
                "rating": item.get("rating"),
                "condition": item.get("condition", "Not specified"),
                "specs": "",
                "shipping": item.get("shipping", "See listing"),
                "url": item.get("url", ""),
            }
        )

    return products


def log_scraped_products(site: str, products: list) -> None:
    """Prints a readable preview of scraper results for debugging."""
    print(f"   [{site}] Returning {len(products)} structured products")
    if not products:
        print(f"   [{site}] No structured products returned")
        return

    for index, product in enumerate(products, start=1):
        print(
            f"   [{site}] Product {index}: "
            f"name={product.get('name')!r}, "
            f"price={product.get('price')}, "
            f"rating={product.get('rating')}, "
            f"condition={product.get('condition')!r}, "
            f"shipping={product.get('shipping')!r}, "
            f"url={product.get('url')!r}"
        )
