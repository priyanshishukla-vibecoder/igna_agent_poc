"""Feasibility validator for parsed search criteria.

Runs after :func:`core.query_parser.parse_query` and before the scrapers so we
can short-circuit obviously impossible queries without paying the cost of a
Playwright run.
"""

import json

from integrations.openai_client import get_openai_client, get_openai_deployment


_DEFAULT_FEASIBLE_RESULT = {
    "feasible": True,
    "reason": "",
    "suggested_min_price": None,
}

SYSTEM_PROMPT = """You are a pricing assistant for a US product shopping agent.

Given a product and a max price, decide: can this product realistically be found
under that price on US marketplaces like Amazon, Best Buy, or eBay?

Key facts to keep in mind:
- eBay includes used, renewed, and refurbished listings which often sell for
  40-60% of the new retail price for phones and electronics.
- A renewed/used flagship phone (Galaxy S25, iPhone 15, Pixel 9) can easily
  be found for $400-600 even if the new price is $800+.
- Only return feasible=false when the price is clearly impossible even for
  used/refurbished listings — not just because the new price is higher.
- When uncertain, return feasible=true. Empty scraper results are fine.

Respond ONLY with JSON, no markdown:
{"feasible": boolean, "reason": string, "suggested_min_price": number | null}

If feasible=true, set reason="" and suggested_min_price=null.
If feasible=false, write a short friendly message and suggest the minimum budget.
"""


def _build_validator_payload(criteria: dict) -> dict:
    return {
        "search_term": criteria.get("search_term"),
        "product": criteria.get("product"),
        "brand": criteria.get("brand"),
        "max_price": criteria.get("max_price"),
    }


def validate_feasibility(criteria: dict) -> dict:
    """Returns a dict with ``feasible``, ``reason``, ``suggested_min_price``.

    Asks the LLM whether the product can be found under the given price.
    Fails open on any error so a valid search is never accidentally blocked.
    """
    if not criteria.get("max_price"):
        return dict(_DEFAULT_FEASIBLE_RESULT)

    payload = _build_validator_payload(criteria)

    try:
        client = get_openai_client()
        deployment = get_openai_deployment()

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0,
            max_tokens=150,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)

        feasible = bool(parsed.get("feasible", True))
        reason = str(parsed.get("reason") or "").strip()
        suggested_min_price = parsed.get("suggested_min_price")

        result = {
            "feasible": feasible,
            "reason": reason if not feasible else "",
            "suggested_min_price": suggested_min_price if not feasible else None,
        }
        print(f"   [IGNA Brain] Feasibility check: {result}")
        return result

    except Exception as exc:
        print(f"   [IGNA Brain] Feasibility check failed ({exc}) - assuming feasible")
        return dict(_DEFAULT_FEASIBLE_RESULT)
