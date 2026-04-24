from core.product_filter import (
    dedupe_products,
    filter_products,
    filter_query_relevant_products,
)
from core.product_recommender import recommend
from core.query_parser import parse_query
from core.summary_generator import generate_summary
from integrations.scraper_runner import run_scraper


def run_research(query: str, max_results_per_site: int = 5) -> dict:
    """Runs the end-to-end IGNA research pipeline."""
    minimum_display_results = 5

    print("[IGNA API] Step 1 - parsing query with Azure OpenAI...")
    criteria = parse_query(query)
    print(f"[IGNA API] Criteria: {criteria}")

    print("[IGNA API] Step 2 - CUA scraper launching...")
    search_term = criteria.get("search_term") or query
    print(f"[IGNA API] Search term: {search_term}")
    raw_products = run_scraper(search_term, max_results_per_site)
    print(f"[IGNA API] Step 2 complete - {len(raw_products)} raw products")

    print("[IGNA API] Step 3 - filtering and ranking...")
    filtered = filter_products(raw_products, criteria)
    display_products = filtered[:]

    if filtered and len(filtered) < minimum_display_results:
        expanded_relevant = filter_query_relevant_products(
            raw_products,
            criteria,
            require_brand=False,
        )
        display_products = dedupe_products(filtered + expanded_relevant)
        print(
            "[IGNA API] Strict filtering found "
            f"{len(filtered)} products; expanded display set to {len(display_products)} "
            "with soft brand fallback"
        )
    elif not filtered:
        display_products = filter_query_relevant_products(
            raw_products,
            criteria,
            require_brand=False,
        )
        print(
            "[IGNA API] Strict filtering returned 0 products; "
            f"soft relevance fallback found {len(display_products)} products"
        )

    top_pick = recommend(filtered, criteria)
    display_recommendation = top_pick if top_pick else recommend(display_products, criteria)
    print(f"[IGNA API] Step 3 complete - {len(display_products)} products")

    print("[IGNA API] Step 4 - generating AI summary...")
    summary = generate_summary(display_products, criteria, display_recommendation)

    return {
        "criteria": criteria,
        "raw_products": raw_products,
        "filtered_products": filtered,
        "display_products": display_products,
        "top_pick": top_pick,
        "display_recommendation": display_recommendation,
        "summary": summary,
    }
