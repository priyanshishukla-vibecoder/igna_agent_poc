# cua_scraper.py
# CUA (Computer Use Agent) — Execution Layer
# Responsible for browser automation and product data extraction
#
# Fix: Python 3.14 on Windows requires WindowsProactorEventLoopPolicy
# for Playwright subprocess creation to work correctly.

import sys
import asyncio

import os

from urllib.parse import quote_plus

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import random
from playwright.async_api import async_playwright

# Constants

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
]

EBAY_CATEGORIES = {
    "smartphone": "9355", "phone": "9355", "laptop": "177",
    "tablet": "171485", "headphones": "112529", "tv": "11071",
    "camera": "625", "smartwatch": "178893",
}

BESTBUY_CATEGORIES = {
    "smartphone": "cat09000", "phone": "cat09000",
    "laptop": "abcat0502000", "tablet": "pcmcat1575399559049",
    "headphones": "abcat0204000", "tv": "abcat0101000",
    "camera": "abcat0400000", "smartwatch": "smartwatches",
}

# ── Browser Setup 

async def get_stealth_page(playwright):
    """Launch Chromium with anti-bot-detection settings."""
    browser = await playwright.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)
    page = await context.new_page()
    return browser, page


# ── Helpers ────────────────────────────────────────────────────────────────────

async def human_delay(min_ms: int = 800, max_ms: int = 2000):
    """Random delay to mimic human browsing pace."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def get_product_keyword(query: str) -> str:
    return query.strip().split()[0].lower() if query.strip() else ""


def is_relevant_product_title(query: str, title: str) -> bool:
    """Keeps obviously unrelated products out of result sets."""
    keyword = get_product_keyword(query)
    normalized = title.lower()

    aliases = {
        "tablet": ["tablet", "ipad", "galaxy tab", "fire hd", "fire max", "tab "],
        "laptop": ["laptop", "notebook", "chromebook", "macbook", "thinkpad", "ideapad", "vivobook", "zenbook"],
        "phone": ["phone", "smartphone", "iphone", "galaxy s", "pixel"],
        "smartphone": ["phone", "smartphone", "iphone", "galaxy s", "pixel"],
        "headphones": ["headphones", "earbuds", "airpods", "headset"],
        "tv": [" tv", "smart tv", "oled", "qled"],
        "camera": ["camera", "dslr", "mirrorless", "gopro"],
        "smartwatch": ["smartwatch", "watch", "apple watch", "galaxy watch", "fitbit"],
    }

    terms = aliases.get(keyword)
    if not terms:
        return True

    return any(term in normalized for term in terms)


def build_products(raw_items: list, site: str, max_results: int) -> list:
    """Converts raw JS-extracted dicts into structured product records."""
    products = []
    for item in raw_items[:max_results]:
        name = item.get("title", "").replace("\n", " ").replace(
            "Opens in a new window or tab", ""
        ).strip()
        if not name:
            continue
        products.append({
            "site":      site,
            "name":      name,
            "price":     item.get("price"),
            "rating":    item.get("rating"),
            "condition": item.get("condition", "Not specified"),
            "specs":     "",
            "shipping":  item.get("shipping", "See listing"),
            "url":       item.get("url", "")
        })
    return products


def log_scraped_products(site: str, products: list) -> None:
    """Prints a readable preview of scraper results for debugging."""
    print(f"   [{site}] Returning {len(products)} structured products")
    if not products:
        print(f"   [{site}] No structured products returned")
        return

    for index, product in enumerate(products, start=1):
        print(
            f"   [{site}] Product {index}: "
            f"name={product.get('name')!r}, "
            f"price={product.get('price')}, "
            f"rating={product.get('rating')}, "
            f"condition={product.get('condition')!r}, "
            f"shipping={product.get('shipping')!r}, "
            f"url={product.get('url')!r}"
        )


# ── eBay Scraper ───────────────────────────────────────────────────────────────

async def scrape_ebay(
    query: str,
    max_results: int = 5,
    sort: str = "15",
    label: str = "eBay"
) -> list:
    """Scrapes eBay search results scoped to a product category."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as p:
        browser, page = await get_stealth_page(p)
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

            raw_items = await page.evaluate(r"""() => {
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
            }""")

            print(f"   [{label}] Found {len(raw_items)} items")
            products = build_products(raw_items, label, max_results)
            log_scraped_products(label, products)

        except Exception as e:
            print(f"   [{label}] Error: {e}")
            try:
                await page.screenshot(path=f"data/error_{label.lower()[:10]}.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products


# ── Best Buy Scraper ───────────────────────────────────────────────────────────

async def scrape_bestbuy(query: str, max_results: int = 5) -> list:
    """Scrapes Best Buy with category filter and country popup handling."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as p:
        browser, page = await get_stealth_page(p)
        try:
            keyword = get_product_keyword(query)
            category_id = BESTBUY_CATEGORIES.get(keyword, "")
            cat_param = f"&cp={category_id}" if category_id else ""

            search_url = (
                f"https://www.bestbuy.com/site/searchpage.jsp"
                f"?st={query.replace(' ', '+')}&sort=pricelow{cat_param}"
            )

            print(f"   [Best Buy] Navigating...")
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

            raw_items = await page.evaluate(r"""() => {
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

                    items.push({ title, price, rating, shipping, condition: 'New', url });
                });

                const seen = new Set();
                return items.filter(item => {
                    if (seen.has(item.title)) return false;
                    seen.add(item.title);
                    return true;
                });
            }""")

            print(f"   [Best Buy] Found {len(raw_items)} items")
            products = build_products(raw_items, "Best Buy", max_results)
            log_scraped_products("Best Buy", products)

        except Exception as e:
            print(f"   [Best Buy] Error: {e}")
            try:
                await page.screenshot(path="data/error_bestbuy.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products


# ── Amazon Scraper ─────────────────────────────────────────────────────────────

async def scrape_amazon(query: str, max_results: int = 5) -> list:
    """Scrapes Amazon with stealth handling and category extraction."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as p:
        browser, page = await get_stealth_page(p)
        try:
            search_url = f"https://www.amazon.com/s?k={quote_plus(query)}&language=en_US"

            print(f"   [Amazon] Navigating...")
            await page.context.add_cookies([
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
            ])
            # Set extra headers for Amazon
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Referer": "https://www.google.com/",
                "Accept-Language": "en-US,en;q=0.9",
            })

            for attempt in range(2):
                await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                await human_delay(2000, 3000)
                
                content = await page.content()
                if "Type the characters" in content or "Sorry! Something went wrong" in content:
                    print(f"   [Amazon] Bot check detected, retrying (attempt {attempt+1}/2)...")
                    await human_delay(3000, 5000)
                    continue
                else:
                    break

            print(f"   [Amazon] Final URL: {page.url}")
            if "amazon.in" in page.url:
                print("   [Amazon] Warning: redirected to amazon.in; USD prices may not be available")

            await page.evaluate("window.scrollBy(0, 800)")
            await human_delay(1500, 2500)
            await page.screenshot(path="data/debug_amazon.png")

            raw_items = await page.evaluate(r"""() => {
                const items = [];
                // Amazon frequently changes card structures
                const cards = document.querySelectorAll('div[data-component-type="s-search-result"], .s-result-item[data-asin]:not([data-asin=""])');
                
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
                
                // Deduplicate logic locally
                const seen = new Set();
                return items.filter(item => {
                    if (seen.has(item.title)) return false;
                    seen.add(item.title);
                    return true;
                });
            }""")

            print(f"   [Amazon] Found {len(raw_items)} items")
            filtered_items = [
                item for item in raw_items
                if is_relevant_product_title(query, item.get("title", ""))
            ]
            print(f"   [Amazon] Relevant items after filtering: {len(filtered_items)}")
            products = build_products(filtered_items, "Amazon", max_results)
            log_scraped_products("Amazon", products)

        except Exception as e:
            print(f"   [Amazon] Error: {e}")
            try:
                await page.screenshot(path="data/error_amazon.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return products







# ── Orchestrator ───────────────────────────────────────────────────────────────

async def scrape_all(query: str, max_per_site: int = 5) -> list:
    """Runs all scrapers sequentially and combines deduplicated results."""
    all_products = []

    print("   → Scraping eBay (lowest price)...")
    ebay_low = await scrape_ebay(query, max_per_site, sort="15", label="eBay")
    all_products.extend(ebay_low)
    print(f"   → eBay (low price): {len(ebay_low)} products\n")

    print("   → Scraping eBay (top rated)...")
    ebay_top = await scrape_ebay(query, max_per_site, sort="25", label="eBay (top rated)")
    all_products.extend(ebay_top)
    print(f"   → eBay (top rated): {len(ebay_top)} products\n")

    print("   → Scraping Best Buy...")
    bestbuy = await scrape_bestbuy(query, max_per_site)
    all_products.extend(bestbuy)
    print(f"   → Best Buy: {len(bestbuy)} products\n")

    print("   → Scraping Amazon...")
    amazon_items = await scrape_amazon(query, max_per_site)
    all_products.extend(amazon_items)
    print(f"   → Amazon: {len(amazon_items)} products\n")

    seen = set()
    unique = []
    for prod in all_products:
        key = (prod["site"], prod["name"][:60])
        if key not in seen:
            seen.add(key)
            unique.append(prod)

    print(f"   → Total (deduplicated): {len(unique)} products")
    return unique


# ── Public Entry Point (terminal use only) ─────────────────────────────────────

def run_scraper(query: str, max_per_site: int = 5) -> list:
    """
    Synchronous wrapper for main.py terminal use only.
    Do NOT call this from api.py — use await scrape_all() instead.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(scrape_all(query, max_per_site))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return asyncio.run(scrape_all(query, max_per_site))
