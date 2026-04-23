# igna_brain.py
# IGNA Brain Layer — Orchestration, Parsing, Filtering, Ranking
#
# parse_query() uses Azure OpenAI GPT-5-mini instead of regex.
# This means ANY natural language query works correctly.
# Falls back to regex if Azure OpenAI is unreachable.

import os
import re
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()


# ── Azure OpenAI client ────────────────────────────────────────────────────────

def get_openai_client() -> AzureOpenAI:
    """
    Initialises the Azure OpenAI client from .env credentials.
    Best practice: never hardcode keys — always load from environment.
    """
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )


# ── Query Parser (Azure OpenAI) ────────────────────────────────────────────────

def parse_query(query: str) -> dict:
    """
    Converts a natural language query into structured search criteria
    using Azure OpenAI GPT-5-mini.

    Examples:
      "Find me a good cheap Samsung phone"
        → brand=Samsung, product=smartphone
      "Best laptop under a grand with 16 gigs"
        → product=laptop, max_price=1000, min_ram_gb=16
      "iPhone under 500 bucks"
        → product=smartphone, brand=Apple, max_price=500

    Falls back to regex if Azure OpenAI is unavailable.
    """
    try:
        client = get_openai_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")

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
                {"role": "user",   "content": query}
            ],
            temperature=0,
            max_tokens=200,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        criteria = json.loads(raw)

        print(f"   [IGNA Brain] Azure OpenAI parsed: {criteria}")
        return criteria

    except Exception as e:
        print(f"   [IGNA Brain] Azure OpenAI unavailable ({e}) — falling back to regex")
        return _parse_query_regex(query)


def _parse_query_regex(query: str) -> dict:
    """
    Regex fallback parser — used when Azure OpenAI is unavailable.
    Less intelligent but always works offline.
    """
    criteria = {
        "product":        None,
        "max_price":      None,
        "min_ram_gb":     None,
        "min_storage_gb": None,
        "brand":          None,
        "condition":      None,
        "sites":          ["eBay", "Best Buy", "Amazon"]
    }
    q = query.lower()

    for keyword in ["smartphone", "phone", "laptop", "tablet", "headphones", "tv", "camera"]:
        if keyword in q:
            criteria["product"] = keyword
            break

    price_match = re.search(r'(?:under|below|max|less than)\s*\$?(\d+)', q)
    if price_match:
        criteria["max_price"] = int(price_match.group(1))

    ram_match = re.search(r'(\d+)\s*gb\s*(?:of\s*)?ram', q)
    if ram_match:
        criteria["min_ram_gb"] = int(ram_match.group(1))

    storage_match = re.search(r'(\d+)\s*gb\s*(?:of\s*)?storage', q)
    if storage_match:
        criteria["min_storage_gb"] = int(storage_match.group(1))

    for brand in ["Samsung", "Apple", "OnePlus", "Google", "Sony", "Dell", "HP", "Lenovo"]:
        if brand.lower() in q:
            criteria["brand"] = brand
            break

    return criteria


# ── Filter Engine ──────────────────────────────────────────────────────────────

def filter_products(products: list, criteria: dict) -> list:
    """
    Filters raw scraped products against the structured criteria.
    Removes products that do not meet price, RAM, storage, or brand requirements.
    """
    filtered = []

    for p in products:

        # Price filter
        if criteria.get("max_price") and p.get("price"):
            if p["price"] > criteria["max_price"]:
                continue

        # Brand filter — checks if brand name appears in product title
        if criteria.get("brand"):
            name_lower = (p.get("name") or "").lower()
            if criteria["brand"].lower() not in name_lower:
                continue

        # RAM filter
        if criteria.get("min_ram_gb"):
            combined = f"{p.get('name', '')} {p.get('specs', '')}".lower()
            ram_match = re.search(r'(\d+)\s*gb\s*(?:ram|memory)', combined)
            if ram_match:
                if int(ram_match.group(1)) < criteria["min_ram_gb"]:
                    continue

        # Storage filter
        if criteria.get("min_storage_gb"):
            combined = f"{p.get('name', '')} {p.get('specs', '')}".lower()
            storage_match = re.search(r'(\d+)\s*(?:gb|tb)\s*(?:ssd|storage|hdd|flash)', combined)
            if storage_match:
                if int(storage_match.group(1)) < criteria["min_storage_gb"]:
                    continue

        # Condition filter
        if criteria.get("condition"):
            product_condition = (p.get("condition") or "").lower()
            if criteria["condition"] == "new" and "pre" in product_condition:
                continue
            if criteria["condition"] == "pre-owned" and product_condition == "new":
                continue

        filtered.append(p)

    # Sort: price ascending, then rating descending
    filtered.sort(key=lambda x: (
        x.get("price") or 9999,
        -(x.get("rating") or 0)
    ))

    return filtered


# ── Recommender ────────────────────────────────────────────────────────────────

def recommend(products: list) -> dict | None:
    """Returns the top recommended product after sorting."""
    return products[0] if products else None


# ── AI Summary ─────────────────────────────────────────────────────────────────

def generate_summary(products: list, criteria: dict, recommendation: dict) -> str:
    """
    Uses Azure OpenAI to generate a human-readable business summary
    of the search results and recommendation.

    This is the IGNA Insight layer — turning raw scraped data into
    actionable language for the end user or stakeholder.
    """
    if not products:
        return "No products found matching your criteria."

    try:
        client = get_openai_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")

        top5 = products[:5]
        product_lines = "\n".join([
            f"- {p['name'][:60]} | ${p.get('price', 'N/A')} | "
            f"{p.get('condition', 'N/A')} | {p.get('site', 'N/A')}"
            for p in top5
        ])

        rec_line = (
            f"{recommendation['name'][:60]} at ${recommendation.get('price', 'N/A')}"
            if recommendation else "None"
        )

        prompt = f"""You are IGNA, an AI research agent. Write a short 2-3 sentence
business summary of these product search results. Be specific about prices and value.

Search criteria: {json.dumps(criteria)}
Top results:
{product_lines}
Top recommendation: {rec_line}

Write the summary now:"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"   [IGNA Brain] Summary generation failed: {e}")
        if recommendation:
            return (
                f"Found {len(products)} products matching your criteria. "
                f"Top recommendation: {recommendation.get('name', 'N/A')[:60]} "
                f"at ${recommendation.get('price', 'N/A')} "
                f"from {recommendation.get('site', 'N/A')}."
            )
        return f"Found {len(products)} products matching your criteria."