import json
import re

from integrations.openai_client import get_openai_client, get_openai_deployment


def normalize_storage_gb(value: int | float | str | None, query: str) -> int | None:
    """Normalizes storage values to GB using deterministic query parsing."""
    query_lower = query.lower()
    tb_match = re.search(r"\b(\d+)\s*tb\b", query_lower)
    if tb_match:
        return int(tb_match.group(1)) * 1024

    gb_match = re.search(r"\b(\d+)\s*gb\b", query_lower)
    if gb_match:
        return int(gb_match.group(1))

    if value is None:
        return None

    return int(float(value))


def normalize_criteria(criteria: dict, query: str) -> dict:
    """Applies deterministic cleanup after LLM or regex parsing."""
    criteria["min_storage_gb"] = normalize_storage_gb(criteria.get("min_storage_gb"), query)
    return criteria


def parse_query(query: str) -> dict:
    """
    Converts a natural language query into structured search criteria
    using Azure OpenAI GPT-5-mini.

    Falls back to regex if Azure OpenAI is unavailable.
    """
    try:
        client = get_openai_client()
        deployment = get_openai_deployment()

        system_prompt = """You are a product search query parser for an eCommerce research agent.

Extract structured search criteria from the user's natural language query.
Respond ONLY with a valid JSON object, with no explanation, markdown, or backticks.

JSON schema:
{
  "search_term": string or null,
  "product": string or null,
  "max_price": number or null,
  "min_ram_gb": integer or null,
  "min_storage_gb": integer or null,
  "brand": string or null,
  "condition": "new" or "pre-owned" or null,
  "sites": ["eBay", "Best Buy", "Amazon"]
}

Rules:
- search_term: create a short ecommerce-ready search phrase that keeps important buying constraints and removes filler words
- product: normalize to lowercase singular (e.g. "smartphones" -> "smartphone")
- max_price: extract number only (e.g. "under $500" -> 500, "under a grand" -> 1000)
- min_ram_gb: extract GB number only (e.g. "8GB RAM" -> 8, "16 gigs" -> 16)
- min_storage_gb: always convert storage to GB (e.g. "256GB storage" -> 256, "1TB" -> 1024, "2TB" -> 2048)
- brand: capitalize properly (e.g. "samsung" -> "Samsung", "apple" -> "Apple")
- condition: only set if explicitly mentioned
- Keep useful modifiers like audience, material, style, and price constraints inside search_term
- Remove filler words like "find", "show me", "best", "good", "please", "I want"
- sites: always return ["eBay", "Best Buy", "Amazon"]"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=200,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        criteria = normalize_criteria(json.loads(raw), query)

        print(f"   [IGNA Brain] Azure OpenAI parsed: {criteria}")
        return criteria

    except Exception as exc:
        print(f"   [IGNA Brain] Azure OpenAI unavailable ({exc}) - falling back to regex")
        return parse_query_regex(query)


def parse_query_regex(query: str) -> dict:
    """Regex fallback parser used when Azure OpenAI is unavailable."""
    criteria = {
        "search_term": None,
        "product": None,
        "max_price": None,
        "min_ram_gb": None,
        "min_storage_gb": None,
        "brand": None,
        "condition": None,
        "sites": ["eBay", "Best Buy", "Amazon"],
    }
    query_lower = query.lower()

    for keyword in [
        "smartphone",
        "phone",
        "laptop",
        "tablet",
        "headphones",
        "tv",
        "camera",
    ]:
        if keyword in query_lower:
            criteria["product"] = keyword
            break

    price_match = re.search(r"(?:under|below|max|less than)\s*\$?(\d+)", query_lower)
    if price_match:
        criteria["max_price"] = int(price_match.group(1))

    ram_match = re.search(r"(\d+)\s*gb\s*(?:of\s*)?ram", query_lower)
    if ram_match:
        criteria["min_ram_gb"] = int(ram_match.group(1))

    storage_match = re.search(r"(\d+)\s*(gb|tb)(?:\s*(?:of\s*)?storage)?", query_lower)
    if storage_match:
        value = int(storage_match.group(1))
        unit = storage_match.group(2)
        criteria["min_storage_gb"] = value * 1024 if unit == "tb" else value

    for brand in ["Samsung", "Apple", "OnePlus", "Google", "Sony", "Dell", "HP", "Lenovo"]:
        if brand.lower() in query_lower:
            criteria["brand"] = brand
            break

    criteria = normalize_criteria(criteria, query)
    criteria["search_term"] = build_search_term(query, criteria)
    return criteria


def build_search_term(query: str, criteria: dict) -> str:
    """
    Builds a short ecommerce-friendly search phrase.
    Keeps useful shopping qualifiers and removes conversational filler.
    """
    normalized = query.lower().strip()
    normalized = re.sub(r"[^\w\s$'-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    filler_phrases = [
        "find me",
        "find",
        "show me",
        "i want",
        "i need",
        "looking for",
        "can you find",
        "can you show me",
        "best",
        "good",
        "top",
        "please",
    ]

    cleaned = normalized
    for phrase in filler_phrases:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = []

    brand = criteria.get("brand")
    product = criteria.get("product")

    if brand:
        parts.append(brand.lower())

    if product and product not in cleaned:
        parts.append(product)

    audience_patterns = [
        r"\bwomen(?:'s)?\b",
        r"\bmen(?:'s)?\b",
        r"\bkids?\b",
        r"\bboys?\b",
        r"\bgirls?\b",
    ]
    for pattern in audience_patterns:
        match = re.search(pattern, cleaned)
        if match:
            parts.append(match.group(0))

    material_style_matches = re.findall(
        r"\b(cotton|linen|leather|copper|steel|formal|casual|oversized|wireless|gaming|office)\b",
        cleaned,
    )
    parts.extend(material_style_matches)

    if product:
        parts.append(product)

    if criteria.get("max_price") is not None:
        parts.append(f"under ${int(criteria['max_price'])}")

    if criteria.get("min_ram_gb"):
        parts.append(f"{criteria['min_ram_gb']}gb ram")

    if criteria.get("min_storage_gb"):
        parts.append(f"{criteria['min_storage_gb']}gb storage")

    if criteria.get("condition"):
        parts.append(criteria["condition"])

    search_term = " ".join(dict.fromkeys(part for part in parts if part)).strip()
    return search_term or cleaned or query.strip()
