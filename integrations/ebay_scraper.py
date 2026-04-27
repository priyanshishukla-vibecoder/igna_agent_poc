import os

from playwright.async_api import async_playwright

from core.cancellation import CancelContext, FlowCancelled
from integrations.browser import get_stealth_page, human_delay, register_cancelable_browser
from integrations.scraper_support import (
    EBAY_CATEGORIES,
    build_products,
    get_product_keyword,
    infer_condition_from_text,
    is_truly_new_item,
    log_raw_scraper_items,
    log_scraped_products,
)


def get_ebay_condition_param(query: str) -> str:
    """
    Maps user condition intent to eBay item condition codes.
    Defaults to New-only results for faster, cleaner scraping.
    """
    query_lower = query.lower()
    if "open box" in query_lower:
        return "1500"
    if "refurbished" in query_lower or "renewed" in query_lower:
        return "2000"
    if "used" in query_lower or "pre-owned" in query_lower or "pre owned" in query_lower:
        return "3000"
    return "1000"


async def navigate_ebay_search(
    page,
    search_url: str,
    label: str,
    cancel_context: CancelContext | None = None,
) -> None:
    """
    Warm up the eBay session first, then load search with one retry if the edge
    returns an access-denied page.
    """
    await page.set_extra_http_headers(
        {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )

    for attempt in range(2):
        if cancel_context is not None:
            cancel_context.raise_if_cancelled()

        if attempt == 0:
            print(f"   [{label}] Opening eBay homepage...")
            await page.goto("https://www.ebay.com/", timeout=30000, wait_until="domcontentloaded")
            await human_delay(1800, 2600, cancel_context=cancel_context)

        print(f"   [{label}] Navigating to search (attempt {attempt + 1}/2)...")
        await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
        await human_delay(2200, 3200, cancel_context=cancel_context)

        page_text = (await page.text_content("body") or "").lower()
        page_title = (await page.title() or "").lower()
        blocked = "access denied" in page_title or "access denied" in page_text

        if not blocked:
            return

        print(f"   [{label}] Access denied page detected, retrying with a fresh eBay session...")
        await page.context.clear_cookies()
        await human_delay(3000, 4500, cancel_context=cancel_context)
        await page.goto("https://www.ebay.com/", timeout=30000, wait_until="domcontentloaded")
        await human_delay(2200, 3200, cancel_context=cancel_context)

    raise RuntimeError("eBay returned Access Denied for the search page")


async def scrape_ebay(
    query: str,
    max_results: int = 5,
    sort: str = "15",
    label: str = "eBay",
    cancel_context: CancelContext | None = None,
) -> list:
    """Scrapes eBay search results scoped to a product category."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as playwright:
        browser, page = await get_stealth_page(playwright)
        close_browser_callback = register_cancelable_browser(browser, cancel_context)
        try:
            if cancel_context is not None:
                cancel_context.raise_if_cancelled()

            keyword = get_product_keyword(query)
            category_id = EBAY_CATEGORIES.get(keyword, "")
            cat_param = f"&_sacat={category_id}" if category_id else ""
            condition_code = get_ebay_condition_param(query)

            if category_id:
                print(f"   [{label}] Category: {category_id} ({keyword})")

            search_url = (
                f"https://www.ebay.com/sch/i.html"
                f"?_nkw={query.replace(' ', '+')}"
                f"&_sop={sort}&LH_BIN=1&LH_ItemCondition={condition_code}{cat_param}"
            )

            print(f"   [{label}] Navigating...")
            await navigate_ebay_search(page, search_url, label, cancel_context=cancel_context)
            await page.wait_for_selector(".srp-river-results li", timeout=15000)
            await page.evaluate("window.scrollBy(0, 600)")
            await human_delay(2000, 3000, cancel_context=cancel_context)

            screenshot_name = label.lower().replace(" ", "_").replace("(", "").replace(")", "")
            await page.screenshot(path=f"data/debug_{screenshot_name}.png")

            raw_items = await page.evaluate(
                r"""() => {
                    const items = [];
                    document.querySelectorAll('li').forEach(li => {
                        const text = li.innerText || '';
                        if (!text.includes('$') || text.length < 20) return;
                        if (li.querySelectorAll('li').length > 0) return;

                        const titleEl = li.querySelector('h3, [class*="title"], [class*="Title"]');
                        const title = titleEl
                            ? titleEl.innerText.trim()
                            : li.innerText.split('\n')[0].trim();

                        if (!title || title.length < 5) return;
                        if (title.toLowerCase().includes('shop on ebay')) return;
                        if (title.startsWith('$')) return;

                        const priceMatch = text.match(/\$([\d,]+(?:\.[\d]+)?)/);
                        const price = priceMatch ? parseFloat(priceMatch[1].replace(/,/g, '')) : null;
                        if (!price) return;

                        const condMatch = text.match(/(Pre-Owned|New|Refurbished|Open Box|Used)/i);
                        const condition = condMatch ? condMatch[1] : 'Not specified';

                        const shipMatch = text.match(/(Free shipping|\+?\$[\d.]+ shipping)/i);
                        const shipping = shipMatch ? shipMatch[1] : 'See listing';

                        const linkEl = li.querySelector('a[href*="ebay.com/itm"]');
                        const url = linkEl ? linkEl.href : null;

                        const ratingEl = li.querySelector('.s-item__seller-info-text');
                        let rating = null;
                        if (ratingEl) {
                            const m = ratingEl.innerText.match(/([\d]+\.?[\d]*)\s*%/);
                            if (m) rating = parseFloat(m[1]);
                        }

                        items.push({ title, price, condition, shipping, url, rating });
                    });
                    return items;
                }"""
            )

            print(f"   [{label}] Found {len(raw_items)} items")
            log_raw_scraper_items(label, raw_items)
            filtered_items = [
                {
                    **item,
                    "condition": infer_condition_from_text(
                        item.get("title"),
                        item.get("condition"),
                    ),
                }
                for item in raw_items
                if is_truly_new_item(item.get("title"), item.get("condition"))
            ]
            print(f"   [{label}] Truly new items after condition filter: {len(filtered_items)}")
            products = build_products(filtered_items, label, max_results)
            log_scraped_products(label, products)

        except FlowCancelled:
            print(f"   [{label}] Cancelled")
            raise
        except Exception as exc:
            print(f"   [{label}] Error: {exc}")
            try:
                await page.screenshot(path=f"data/error_{label.lower()[:10]}.png")
            except Exception:
                pass
        finally:
            if cancel_context is not None and close_browser_callback is not None:
                cancel_context.unregister_callback(close_browser_callback)
            await browser.close()

    return products
