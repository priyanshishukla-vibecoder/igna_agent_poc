import os
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from integrations.browser import get_stealth_page, human_delay
from integrations.scraper_support import (
    build_products,
    is_relevant_product_title,
    log_scraped_products,
)


async def scrape_amazon(query: str, max_results: int = 5) -> list:
    """Scrapes Amazon with stealth handling and category extraction."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as playwright:
        browser, page = await get_stealth_page(playwright)
        try:
            search_url = f"https://www.amazon.com/s?k={quote_plus(query)}&language=en_US"

            print("   [Amazon] Navigating...")
            await page.context.add_cookies(
                [
                    {
                        "name": "i18n-prefs",
                        "value": "USD",
                        "domain": ".amazon.com",
                        "path": "/",
                    },
                    {
                        "name": "lc-main",
                        "value": "en_US",
                        "domain": ".amazon.com",
                        "path": "/",
                    },
                ]
            )
            await page.set_extra_http_headers(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Referer": "https://www.google.com/",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )

            for attempt in range(2):
                await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                await human_delay(2000, 3000)

                content = await page.content()
                if "Type the characters" in content or "Sorry! Something went wrong" in content:
                    print(f"   [Amazon] Bot check detected, retrying (attempt {attempt + 1}/2)...")
                    await human_delay(3000, 5000)
                    continue
                break

            print(f"   [Amazon] Final URL: {page.url}")
            if "amazon.in" in page.url:
                print("   [Amazon] Warning: redirected to amazon.in; USD prices may not be available")

            await page.evaluate("window.scrollBy(0, 800)")
            await human_delay(1500, 2500)
            await page.screenshot(path="data/debug_amazon.png")

            raw_items = await page.evaluate(
                r"""() => {
                    const items = [];
                    const cards = document.querySelectorAll(
                        'div[data-component-type="s-search-result"], .s-result-item[data-asin]:not([data-asin=""])'
                    );

                    cards.forEach(el => {
                        const titleEl = el.querySelector('h2 a span, h2 span, [class*="a-color-base a-text-normal"]');
                        const title = titleEl ? titleEl.innerText.trim() : null;
                        if (!title || title.length < 5) return;

                        const priceSymbolEl = el.querySelector('.a-price-symbol');
                        const priceSymbol = priceSymbolEl ? priceSymbolEl.innerText.trim() : '';
                        if (priceSymbol && priceSymbol !== '$') return;

                        const priceWhole = el.querySelector('.a-price-whole');
                        const priceFraction = el.querySelector('.a-price-fraction');
                        let price = null;
                        if (priceWhole) {
                            const whole = priceWhole.innerText.replace(/[^\d]/g, '');
                            const frac = priceFraction ? priceFraction.innerText : '00';
                            price = parseFloat(`${whole}.${frac}`);
                        }
                        if (!price) {
                             const rawPrice = el.querySelector('.a-offscreen');
                             if (rawPrice && rawPrice.innerText.trim().startsWith('$')) {
                                 price = parseFloat(rawPrice.innerText.replace('$', '').replace(/,/g, '').trim());
                             }
                        }
                        if (!price) return;

                        const ratingEl = el.querySelector('i[class*="a-icon-star"] span, span[aria-label*="out of 5"]');
                        let rating = null;
                        if (ratingEl) {
                            const label = ratingEl.innerText || ratingEl.getAttribute('aria-label');
                            if (label) {
                                const m = String(label).match(/([\d]+\.?[\d]*)/);
                                if (m) rating = parseFloat(m[1]);
                            }
                        }

                        const shippingCandidates = Array.from(
                            el.querySelectorAll(
                                'span[aria-label*="delivery"], span[aria-label*="shipping"], [data-cy="delivery-recipe"], [data-cy="delivery-estimate"]'
                            )
                        );
                        const shippingText = shippingCandidates
                            .map(node => node.innerText || node.getAttribute('aria-label') || '')
                            .find(text => /delivery|shipping|arrives|overnight|today|tomorrow/i.test(text));
                        const shipping = shippingText ? shippingText.trim() : 'See listing';

                        const linkEl = el.querySelector('h2 a, a.a-link-normal.s-no-outline');
                        const url = linkEl ? 'https://www.amazon.com' + linkEl.getAttribute('href') : null;

                        items.push({ title, price, rating, shipping, condition: 'New', url });
                    });

                    const seen = new Set();
                    return items.filter(item => {
                        if (seen.has(item.title)) return false;
                        seen.add(item.title);
                        return true;
                    });
                }"""
            )

            print(f"   [Amazon] Found {len(raw_items)} items")
            filtered_items = [
                item
                for item in raw_items
                if is_relevant_product_title(query, item.get("title", ""))
            ]
            print(f"   [Amazon] Relevant items after filtering: {len(filtered_items)}")
            products = build_products(filtered_items, "Amazon", max_results)
            log_scraped_products("Amazon", products)

        except Exception as exc:
            print(f"   [Amazon] Error: {exc}")
            try:
                await page.screenshot(path="data/error_amazon.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products
