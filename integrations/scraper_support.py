import json


BESTBUY_CATEGORIES = {
    "smartphone": "pcat17071",
    "phone": "pcat17071",
    "iphone": "pcat17071",
    "galaxy": "pcat17071",
    "pixel": "pcat17071",
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

NON_NEW_CONDITION_KEYWORDS = {
    "renewed",
    "renewed premium",
    "refurbished",
    "open box",
    "used",
    "pre-owned",
    "pre owned",
    "excellent",
    "very good",
    "good",
    "fair",
    "mint",
    "sold out",
}

EXPLICIT_NEW_KEYWORDS = {
    "brand new",
    "factory sealed",
    "new sealed",
    "new",
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


def normalize_condition_text(text: str | None) -> str:
    return " ".join(str(text or "").lower().split())


def infer_condition_from_text(title: str | None, condition: str | None = None) -> str:
    """
    Normalizes the condition using both the scraped condition and title text.
    This helps catch listings that are mislabeled as "New" but say "Renewed" in the title.
    """
    title_text = normalize_condition_text(title)
    condition_text = normalize_condition_text(condition)
    combined = f"{title_text} {condition_text}".strip()

    if any(keyword in combined for keyword in NON_NEW_CONDITION_KEYWORDS):
        if "renewed premium" in combined:
            return "Renewed Premium"
        if "renewed" in combined:
            return "Renewed"
        if "refurbished" in combined:
            return "Refurbished"
        if "open box" in combined:
            return "Open Box"
        if "pre-owned" in combined or "pre owned" in combined:
            return "Pre-Owned"
        if "used" in combined:
            return "Used"
        if "sold out" in combined:
            return "Unavailable"
        if "mint" in combined:
            return "Used"
        if "excellent" in combined or "very good" in combined or "good" in combined or "fair" in combined:
            return "Used"

    if any(keyword in combined for keyword in EXPLICIT_NEW_KEYWORDS):
        return "New"

    if condition_text:
        return condition

    return "Not specified"


def is_truly_new_item(title: str | None, condition: str | None = None) -> bool:
    """
    Allows only genuinely new items and rejects renewed/refurbished/open-box/used products.
    """
    inferred = normalize_condition_text(infer_condition_from_text(title, condition))
    return inferred in {"new", "not specified"}


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

        inferred_condition = infer_condition_from_text(name, item.get("condition"))

        products.append(
            {
                "site": site,
                "name": name,
                "price": item.get("price"),
                "rating": item.get("rating"),
                "condition": inferred_condition,
                "specs": "",
                "shipping": item.get("shipping", "See listing"),
                "url": item.get("url", ""),
            }
        )

    return products


def log_raw_scraper_items(site: str, items: list, limit: int = 10) -> None:
    """Prints the raw item dictionaries returned by Playwright page evaluation."""
    print(f"   [{site}] Raw Playwright items: {len(items)}")
    if not items:
        print(f"   [{site}] Raw Playwright payload is empty")
        return

    preview = items[:limit]
    for index, item in enumerate(preview, start=1):
        print(
            f"   [{site}] Raw item {index}: "
            f"{json.dumps(item, ensure_ascii=False, default=str)}"
        )

    remaining = len(items) - len(preview)
    if remaining > 0:
        print(f"   [{site}] ... {remaining} more raw items not shown")


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
