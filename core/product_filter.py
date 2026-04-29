import re
from collections import defaultdict


ACCESSORY_KEYWORDS = {
    "case",
    "cover",
    "charger",
    "charging",
    "cable",
    "screen protector",
    "protector",
    "adapter",
    "strap",
    "band",
    "wallet",
    "mount",
    "holder",
    "stand",
    "mag safe",
    "magsafe",
    "silicone",
}

PHONE_HINTS = {"iphone", "smartphone", "phone", "galaxy", "pixel"}
ELECTRONICS_HINTS = {
    "iphone",
    "phone",
    "smartphone",
    "mobile",
    "galaxy",
    "pixel",
    "laptop",
    "notebook",
    "macbook",
    "chromebook",
    "tablet",
    "ipad",
    "headphones",
    "earbuds",
    "airpods",
    "tv",
    "television",
    "camera",
    "smartwatch",
    "watch",
}
NON_NEW_PRODUCT_KEYWORDS = {
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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def is_phone_query(criteria: dict) -> bool:
    text = normalize_text(
        f"{criteria.get('search_term', '')} {criteria.get('product', '')} {criteria.get('brand', '')}"
    )
    return any(hint in text for hint in PHONE_HINTS)


def has_model_number_query(criteria: dict) -> bool:
    search_term = normalize_text(criteria.get("search_term") or "")
    return bool(re.search(r"\b\d{1,2}[a-z]?\b", search_term))


def is_electronics_query(criteria: dict) -> bool:
    """
    Identifies whether the query is within the current POC's electronics-focused scope.
    """
    if criteria.get("min_ram_gb") or criteria.get("min_storage_gb"):
        return True

    text = normalize_text(
        f"{criteria.get('search_term', '')} {criteria.get('product', '')} {criteria.get('brand', '')}"
    )
    return any(hint in text for hint in ELECTRONICS_HINTS)


def requested_storage_match_mode(criteria: dict) -> str | None:
    """
    Determines whether storage should be treated as an exact or minimum requirement.
    For phone model searches like "iphone 17 128GB", storage is treated as exact intent.
    """
    if not criteria.get("min_storage_gb"):
        return None

    if is_phone_query(criteria) and has_model_number_query(criteria):
        return "exact"

    return "minimum"


def extract_storage_value(text: str) -> int | None:
    normalized = normalize_text(text)
    storage_match = re.search(
        r"\b(\d+)\s*(gb|tb)\s*(?:ssd|storage|hdd|flash|rom|memory)?\b",
        normalized,
    )
    if not storage_match:
        return None

    value = int(storage_match.group(1))
    unit = storage_match.group(2)
    if unit == "tb":
        value *= 1024
    return value


def matches_storage_requirement(product: dict, criteria: dict) -> bool:
    mode = requested_storage_match_mode(criteria)
    if not mode:
        return True

    requested = criteria["min_storage_gb"]
    combined = f"{product.get('name', '')} {product.get('specs', '')}"
    extracted = extract_storage_value(combined)

    if extracted is None:
        return mode != "exact"

    if mode == "exact":
        return extracted == requested

    return extracted >= requested


def has_accessory_keyword(title: str) -> bool:
    title_lower = normalize_text(title)
    return any(keyword in title_lower for keyword in ACCESSORY_KEYWORDS)


def has_required_brand(product: dict, criteria: dict) -> bool:
    if not criteria.get("brand"):
        return True
    name_lower = normalize_text(product.get("name") or "")
    return criteria["brand"].lower() in name_lower


def is_truly_new_product(product: dict) -> bool:
    combined = normalize_text(
        f"{product.get('name', '')} {product.get('condition', '')}"
    )
    return not any(keyword in combined for keyword in NON_NEW_PRODUCT_KEYWORDS)


def matches_exact_model(title: str, criteria: dict) -> bool:
    """
    Tightens matching for model-sensitive searches like "iphone 16".
    Prevents "16GB" from being mistaken for iPhone 16.
    """
    if not is_electronics_query(criteria):
        return True

    search_term = normalize_text(criteria.get("search_term") or "")
    title_lower = normalize_text(title)

    iphone_match = re.search(r"\biphone\s*(\d{1,2}[a-z]?)\b", search_term)
    if iphone_match:
        model = iphone_match.group(1)
        return bool(
            re.search(
                rf"\biphone\s*{re.escape(model)}(?:\s*(?:pro|max|plus|mini|e))?\b",
                title_lower,
            )
        )

    pixel_match = re.search(r"\bpixel\s*(\d{1,2}[a-z]?)\b", search_term)
    if pixel_match:
        model = pixel_match.group(1)
        return bool(
            re.search(rf"\bpixel\s*{re.escape(model)}(?:\s*(?:pro|xl|a))?\b", title_lower)
        )

    galaxy_match = re.search(r"\bgalaxy\s*(s\d{1,2}|a\d{1,2}|z\s*fold\s*\d|z\s*flip\s*\d)\b", search_term)
    if galaxy_match:
        model = re.sub(r"\s+", " ", galaxy_match.group(1))
        title_normalized = re.sub(r"\s+", " ", title_lower)
        return f"galaxy {model}" in title_normalized

    return True


def looks_like_installment_price(product: dict, criteria: dict) -> bool:
    """
    Rejects unrealistically low carrier/installment prices for modern phone model queries.
    """
    if not is_electronics_query(criteria) or not is_phone_query(criteria):
        return False

    price = product.get("price")
    if price is None or criteria.get("max_price") is not None:
        return False

    search_term = normalize_text(criteria.get("search_term") or "")
    has_model_number = has_model_number_query(criteria)
    if not has_model_number:
        return False

    site = normalize_text(product.get("site") or "")
    title = normalize_text(product.get("name") or "")
    return price < 100 and ("best buy" in site or "verizon" in title or "at&t" in title or "t-mobile" in title)


def score_product(product: dict, criteria: dict) -> float:
    """
    Scores a product for relevance so recommendation is not based on cheapest-first only.
    """
    score = 0.0
    title = normalize_text(product.get("name") or "")
    search_term = normalize_text(criteria.get("search_term") or "")

    if criteria.get("brand") and criteria["brand"].lower() in title:
        score += 20

    if search_term:
        for token in search_term.split():
            if len(token) > 1 and token in title:
                score += 5

    if is_electronics_query(criteria) and matches_exact_model(title, criteria):
        score += 35

    if product.get("rating"):
        score += min(float(product["rating"]) * 2, 10)

    if product.get("price") is not None:
        score += 5

    if has_accessory_keyword(title):
        score -= 50

    if looks_like_installment_price(product, criteria):
        score -= 40

    return score


def dedupe_products(products: list) -> list:
    """Deduplicates products while preserving order."""
    unique = []
    seen = set()

    for product in products:
        key = (
            normalize_text(product.get("site") or ""),
            normalize_text(product.get("name") or ""),
            product.get("url") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)

    return unique


def filter_query_relevant_products(
    products: list,
    criteria: dict,
    require_brand: bool = True,
    per_site_limit: int | None = None,
) -> list:
    """
    Applies softer relevance checks for display fallback.
    Keeps query-aligned items without requiring every strict filter to pass.
    """
    relevant = []
    search_term = normalize_text(criteria.get("search_term") or "")
    search_tokens = [token for token in search_term.split() if len(token) > 2]

    for product in products:
        title = normalize_text(product.get("name") or "")
        if not title:
            continue

        if has_accessory_keyword(title):
            continue

        condition_text = normalize_text(product.get("condition") or "")
        requested_condition = normalize_text(criteria.get("condition") or "")
        if requested_condition == "new" and not is_truly_new_product(product):
            continue
        if requested_condition in {"pre-owned", "pre owned"} and is_truly_new_product(product):
            continue

        if not matches_exact_model(product.get("name", ""), criteria):
            continue

        if looks_like_installment_price(product, criteria):
            continue

        max_price = criteria.get("max_price")
        if max_price is not None and product.get("price") is not None:
            if product["price"] > max_price:
                continue

        brand = normalize_text(criteria.get("brand") or "")
        if require_brand and brand and brand not in title:
            continue

        product_name = normalize_text(criteria.get("product") or "")
        if product_name and product_name not in title:
            continue

        if search_tokens:
            token_hits = sum(1 for token in search_tokens if token in title)
            required_hits = 1 if len(search_tokens) <= 2 else 2
            if token_hits < required_hits:
                continue

        relevant.append(product)

    relevant.sort(
        key=lambda item: (
            -score_product(item, criteria),
            item.get("price") or 9999,
            -(item.get("rating") or 0),
        )
    )
    deduped = dedupe_products(relevant)
    if not per_site_limit or per_site_limit <= 0:
        return deduped

    per_site_counts: dict[str, int] = defaultdict(int)
    limited = []
    for product in deduped:
        site = normalize_text(product.get("site") or "unknown")
        if per_site_counts[site] >= per_site_limit:
            continue
        per_site_counts[site] += 1
        limited.append(product)

    return limited


def filter_products(products: list, criteria: dict) -> list:
    """
    Filters raw scraped products against structured criteria.
    Removes products that do not meet price, RAM, storage, or brand requirements.
    """
    filtered = []

    for product in products:
        if criteria.get("max_price") and product.get("price"):
            if product["price"] > criteria["max_price"]:
                continue

        if not has_required_brand(product, criteria):
            continue

        if has_accessory_keyword(product.get("name", "")):
            continue

        if not is_truly_new_product(product):
            continue

        if not matches_exact_model(product.get("name", ""), criteria):
            continue

        if looks_like_installment_price(product, criteria):
            continue

        if is_electronics_query(criteria) and criteria.get("min_ram_gb"):
            combined = f"{product.get('name', '')} {product.get('specs', '')}".lower()
            ram_match = re.search(r"(\d+)\s*gb\s*(?:ram|memory)", combined)
            if ram_match and int(ram_match.group(1)) < criteria["min_ram_gb"]:
                continue

        if is_electronics_query(criteria) and not matches_storage_requirement(product, criteria):
            continue

        if criteria.get("condition"):
            product_condition = (product.get("condition") or "").lower()
            if criteria["condition"] == "new" and "pre" in product_condition:
                continue
            if criteria["condition"] == "pre-owned" and product_condition == "new":
                continue

        filtered.append(product)

    filtered.sort(
        key=lambda item: (
            -score_product(item, criteria),
            item.get("price") or 9999,
            -(item.get("rating") or 0),
        )
    )
    return filtered
