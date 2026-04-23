# main.py
# Terminal entry point — runs the full pipeline from the command line
# The API (api.py) and terminal (main.py) both work independently

from igna_brain import parse_query, filter_products, recommend
from cua_scraper import run_scraper
from reporter import print_table, save_csv


def ask_user_criteria() -> str:
    """
    IGNA Brain guided intake.
    Asks structured questions instead of requiring a perfect query string.
    """
    print("\n" + "=" * 55)
    print("  IGNA Competitive Product Research Agent")
    print("=" * 55)
    print("  Let's build your search. Answer a few questions:\n")

    print("  [1] What product are you researching?")
    print("      e.g. smartphone, laptop, tablet, headphones")
    product = input("      > ").strip() or "smartphone"

    print("\n  [2] What is your maximum budget? (press Enter to skip)")
    print("      e.g. 400")
    budget_input = input("      $").strip()
    budget = f"under ${budget_input}" if budget_input else ""

    print("\n  [3] Minimum RAM required? (press Enter to skip)")
    print("      e.g. 6  (for 6GB RAM)")
    ram_input = input("      ").strip()
    ram = f"with at least {ram_input}GB RAM" if ram_input else ""

    print("\n  [4] Minimum storage required? (press Enter to skip)")
    print("      e.g. 128  (for 128GB storage)")
    storage_input = input("      ").strip()
    storage = f"and {storage_input}GB storage" if storage_input else ""

    print("\n  [5] Any brand preference? (press Enter to skip)")
    print("      e.g. Samsung, Apple, OnePlus")
    brand_input = input("      ").strip()
    brand = f"from {brand_input}" if brand_input else ""

    print("\n  [6] Preferred condition?")
    print("      1. Any  2. New only  3. Pre-owned only")
    condition_choice = input("      Enter 1, 2, or 3 (default 1): ").strip()
    condition_map = {"2": "new", "3": "pre-owned"}
    condition_str = condition_map.get(condition_choice, "")

    query_parts = [product, budget, ram, storage, brand, condition_str]
    query = " ".join(part for part in query_parts if part).strip()

    print(f"\n  ✔ Query built: \"{query}\"")
    print("=" * 55 + "\n")

    return query


def run_agent(user_query: str):
    print(f"\n🔍 Processing: {user_query}\n")

    print("⚙️  IGNA parsing query...")
    criteria = parse_query(user_query)
    print(f"   Criteria: {criteria}\n")

    print("🤖 CUA launching browser and scraping...")
    raw_products = run_scraper(user_query, max_per_site=8)
    print(f"   Found {len(raw_products)} raw results\n")

    print("📊 IGNA filtering and ranking results...")
    filtered = filter_products(raw_products, criteria)
    top_pick = recommend(filtered)
    print(f"   {len(filtered)} products match your criteria\n")

    if filtered:
        print_table(filtered[:10], top_pick)
        save_csv(filtered)
    elif raw_products:
        print("⚠️  No products matched all filters.")
        print("   Showing all results without filters instead:\n")
        top_pick = recommend(raw_products)
        print_table(raw_products[:10], top_pick)
        save_csv(raw_products)
    else:
        print("❌ No products found at all. Check your internet or try again.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    query = ask_user_criteria()
    run_agent(query)