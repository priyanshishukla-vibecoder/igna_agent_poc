from core.product_filter import filter_products
from core.product_recommender import recommend
from core.query_parser import parse_query
from core.summary_generator import generate_summary
from integrations.scraper_runner import run_scraper


def run_research(query: str, max_results_per_site: int = 5) -> dict:
    """Runs the end-to-end IGNA research pipeline."""
    print("[IGNA API] Step 1 — parsing query with Azure OpenAI...")
    criteria = parse_query(query)
    print(f"[IGNA API] Criteria: {criteria}")

    print("[IGNA API] Step 2 — CUA scraper launching...")
    raw_products = run_scraper(query, max_results_per_site)
    print(f"[IGNA API] Step 2 complete — {len(raw_products)} raw products")

    print("[IGNA API] Step 3 — filtering and ranking...")
    filtered = filter_products(raw_products, criteria)
    top_pick = recommend(filtered)
    display_products = filtered if filtered else raw_products
    display_recommendation = top_pick if top_pick else recommend(raw_products)
    print(f"[IGNA API] Step 3 complete — {len(display_products)} products")

    print("[IGNA API] Step 4 — generating AI summary...")
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
