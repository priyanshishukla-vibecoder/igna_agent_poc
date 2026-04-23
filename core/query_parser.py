import json
import re

from integrations.openai_client import get_openai_client, get_openai_deployment


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
Respond ONLY with a valid JSON object — no explanation, no markdown, no backticks.

JSON schema:
{
  "product": string or null,
  "max_price": number or null,
  "min_ram_gb": integer or null,
  "min_storage_gb": integer or null,
  "brand": string or null,
  "condition": "new" or "pre-owned" or null,
  "sites": ["eBay", "Best Buy", "Amazon"]
}

Rules:
- product: normalise to lowercase singular (e.g. "smartphones" → "smartphone")
- max_price: extract number only (e.g. "under $500" → 500, "under a grand" → 1000)
- min_ram_gb: extract GB number only (e.g. "8GB RAM" → 8, "16 gigs" → 16)
- min_storage_gb: extract GB number only (e.g. "256GB storage" → 256)
- brand: capitalise properly (e.g. "samsung" → "Samsung", "apple" → "Apple")
- condition: only set if explicitly mentioned
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
        criteria = json.loads(raw)

        print(f"   [IGNA Brain] Azure OpenAI parsed: {criteria}")
        return criteria

    except Exception as exc:
        print(f"   [IGNA Brain] Azure OpenAI unavailable ({exc}) — falling back to regex")
        return parse_query_regex(query)


def parse_query_regex(query: str) -> dict:
    """Regex fallback parser used when Azure OpenAI is unavailable."""
    criteria = {
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

    storage_match = re.search(r"(\d+)\s*gb\s*(?:of\s*)?storage", query_lower)
    if storage_match:
        criteria["min_storage_gb"] = int(storage_match.group(1))

    for brand in ["Samsung", "Apple", "OnePlus", "Google", "Sony", "Dell", "HP", "Lenovo"]:
        if brand.lower() in query_lower:
            criteria["brand"] = brand
            break

    return criteria
