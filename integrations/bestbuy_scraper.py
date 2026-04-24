import os

from playwright.async_api import async_playwright

from integrations.browser import get_stealth_page, human_delay
from integrations.scraper_support import (
    BESTBUY_CATEGORIES,
    build_products,
    get_product_keyword,
    infer_condition_from_text,
    is_truly_new_item,
    log_raw_scraper_items,
    log_scraped_products,
)


async def scrape_bestbuy(query: str, max_results: int = 5) -> list:
    """Scrapes Best Buy with category filter and country popup handling."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as playwright:
        browser, page = await get_stealth_page(playwright)
        try:
            keyword = get_product_keyword(query)
            category_id = BESTBUY_CATEGORIES.get(keyword, "")
            cat_param = f"&cp={category_id}" if category_id else ""

            search_url = (
                f"https://www.bestbuy.com/site/searchpage.jsp"
                f"?st={query.replace(' ', '+')}&sort=pricelow{cat_param}"
            )

            print("   [Best Buy] Navigating...")
            if category_id:
                print(f"   [Best Buy] Category: {category_id} ({keyword})")

            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await human_delay(2000, 3000)

            page_content = await page.content()
            if "Choose a country" in page_content:
                print("   [Best Buy] Country popup — clicking United States...")
                try:
                    await page.get_by_text("United States", exact=False).first.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    await human_delay(1500, 2500)
                    if "searchpage" not in page.url:
                        await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                        await human_delay(2000, 3000)
                except Exception as popup_err:
                    print(f"   [Best Buy] Popup: {popup_err}")
                    await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                    await human_delay(2000, 3000)

            await page.evaluate("window.scrollBy(0, 600)")
            await human_delay(2000, 2500)
            await page.screenshot(path="data/debug_bestbuy.png")

            raw_items = await page.evaluate(
                r"""() => {
                    const items = [];
                    let cards = Array.from(
                        document.querySelectorAll('li.sku-item, [data-sku-id], li[class*="sku"]')
                    );
                    if (cards.length === 0) {
                        cards = Array.from(document.querySelectorAll('li, article'));
                    }
                    cards.forEach(el => {
                        const text = el.innerText || '';
                        if (!text.includes('$') || text.length < 20) return;
                        if (el.querySelectorAll('li').length > 2) return;

                        const titleEl = el.querySelector('.sku-header a, [class*="sku-title"] a, h4, h3');
                        const title = titleEl
                            ? titleEl.innerText.trim()
                            : el.innerText.split('\n')[0].trim();
                        if (!title || title.length < 5) return;

                        const priceEl = el.querySelector(
                            '.priceView-customer-price span, [class*="priceView"] span'
                        );
                        let price = null;
                        if (priceEl) {
                            const m = priceEl.innerText.match(/\$([\d,]+(?:\.[\d]+)?)/);
                            if (m) price = parseFloat(m[1].replace(/,/g, ''));
                        }
                        if (!price) {
                            const m = text.match(/\$([\d,]+(?:\.[\d]+)?)/);
                            if (m) price = parseFloat(m[1].replace(/,/g, ''));
                        }
                        if (!price) return;

                        const ratingEl = el.querySelector('[class*="rating"], .c-ratings-reviews');
                        let rating = null;
                        if (ratingEl) {
                            const label = ratingEl.getAttribute('aria-label') || ratingEl.innerText;
                            const m = String(label).match(/([\d]+\.?[\d]*)/);
                            if (m) rating = parseFloat(m[1]);
                        }

                        const shipEl = el.querySelector('[class*="shipping"], [class*="fulfillment"]');
                        const shipping = shipEl ? shipEl.innerText.trim() : 'See listing';

                        const linkEl = el.querySelector('a[href*="/site/"]');
                        const url = linkEl
                            ? 'https://www.bestbuy.com' + linkEl.getAttribute('href')
                            : null;

                        const titleLower = title.toLowerCase();
                        let condition = 'Not specified';
                        if (
                            titleLower.includes('renewed premium') ||
                            titleLower.includes('renewed') ||
                            titleLower.includes('refurbished') ||
                            titleLower.includes('open box') ||
                            titleLower.includes('used') ||
                            titleLower.includes('pre-owned') ||
                            titleLower.includes('pre owned')
                        ) {
                            condition = title;
                        } else {
                            condition = 'New';
                        }

                        items.push({ title, price, rating, shipping, condition, url });
                    });

                    const seen = new Set();
                    return items.filter(item => {
                        if (seen.has(item.title)) return false;
                        seen.add(item.title);
                        return true;
                    });
                }"""
            )

            print(f"   [Best Buy] Found {len(raw_items)} items")
            log_raw_scraper_items("Best Buy", raw_items)
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
            print(f"   [Best Buy] Truly new items after condition filter: {len(filtered_items)}")
            products = build_products(filtered_items, "Best Buy", max_results)
            log_scraped_products("Best Buy", products)

        except Exception as exc:
            print(f"   [Best Buy] Error: {exc}")
            try:
                await page.screenshot(path="data/error_bestbuy.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products
