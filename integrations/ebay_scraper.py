import os

from playwright.async_api import async_playwright

from integrations.browser import get_stealth_page, human_delay
from integrations.scraper_support import (
    EBAY_CATEGORIES,
    build_products,
    get_product_keyword,
    log_scraped_products,
)


async def scrape_ebay(query: str, max_results: int = 5, sort: str = "15", label: str = "eBay") -> list:
    """Scrapes eBay search results scoped to a product category."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as playwright:
        browser, page = await get_stealth_page(playwright)
        try:
            keyword = get_product_keyword(query)
            category_id = EBAY_CATEGORIES.get(keyword, "")
            cat_param = f"&_sacat={category_id}" if category_id else ""

            if category_id:
                print(f"   [{label}] Category: {category_id} ({keyword})")

            search_url = (
                f"https://www.ebay.com/sch/i.html"
                f"?_nkw={query.replace(' ', '+')}"
                f"&_sop={sort}&LH_BIN=1{cat_param}"
            )

            print(f"   [{label}] Navigating...")
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_selector(".srp-river-results li", timeout=15000)
            await page.evaluate("window.scrollBy(0, 600)")
            await human_delay(2000, 3000)

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
            products = build_products(raw_items, label, max_results)
            log_scraped_products(label, products)

        except Exception as exc:
            print(f"   [{label}] Error: {exc}")
            try:
                await page.screenshot(path=f"data/error_{label.lower()[:10]}.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products
