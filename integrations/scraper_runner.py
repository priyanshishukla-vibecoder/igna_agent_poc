import asyncio
import sys

from core.cancellation import CancelContext
from integrations.amazon_scraper import scrape_amazon
from integrations.bestbuy_scraper import scrape_bestbuy
from integrations.ebay_scraper import scrape_ebay


async def scrape_all(
    query: str,
    max_per_site: int = 5,
    criteria: dict | None = None,
    cancel_context: CancelContext | None = None,
) -> list:
    """Runs all scrapers sequentially and combines deduplicated results."""
    all_products = []

    if cancel_context is not None:
        cancel_context.raise_if_cancelled()

    print("   -> Scraping eBay (top rated)...")
    ebay_top = await scrape_ebay(
        query,
        max_per_site,
        sort="25",
        label="eBay (top rated)",
        cancel_context=cancel_context,
    )
    all_products.extend(ebay_top)
    print(f"   -> eBay (top rated): {len(ebay_top)} products\n")

    if cancel_context is not None:
        cancel_context.raise_if_cancelled()

    print("   -> Scraping Best Buy...")
    bestbuy = await scrape_bestbuy(query, max_per_site, criteria=criteria, cancel_context=cancel_context)
    all_products.extend(bestbuy)
    print(f"   -> Best Buy: {len(bestbuy)} products\n")

    if cancel_context is not None:
        cancel_context.raise_if_cancelled()

    print("   -> Scraping Amazon...")
    amazon_items = await scrape_amazon(query, max_per_site, cancel_context=cancel_context)
    all_products.extend(amazon_items)
    print(f"   -> Amazon: {len(amazon_items)} products\n")

    seen = set()
    unique = []
    for product in all_products:
        key = (product["site"], product["name"][:60])
        if key not in seen:
            seen.add(key)
            unique.append(product)

    print(f"   -> Total (deduplicated): {len(unique)} products")
    return unique


def run_scraper(
    query: str,
    max_per_site: int = 5,
    criteria: dict | None = None,
    cancel_context: CancelContext | None = None,
) -> list:
    """
    Synchronous wrapper for API thread execution and terminal use.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                scrape_all(query, max_per_site, criteria=criteria, cancel_context=cancel_context)
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return asyncio.run(scrape_all(query, max_per_site, criteria=criteria, cancel_context=cancel_context))
