import os
import re
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from integrations.browser import get_stealth_page, human_delay
from integrations.scraper_support import (
    build_products,
    infer_condition_from_text,
    is_relevant_product_title,
    is_truly_new_item,
    log_raw_scraper_items,
    log_scraped_products,
)


def parse_amazon_price_text(text: str | None) -> float | None:
    """Parses a currency string such as '$1,114.97' into a float."""
    if not text:
        return None

    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return None

    has_comma = "," in cleaned
    has_dot = "." in cleaned

    if has_comma and has_dot:
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif has_comma:
        parts = cleaned.split(",")
        last = parts[-1]
        cleaned = "".join(parts[:-1]) + "." + last if len(last) == 2 else "".join(parts)

    try:
        value = float(cleaned)
    except ValueError:
        return None

    return value if value > 0 else None


async def enrich_amazon_missing_prices(page, items: list, limit: int) -> list:
    """
    Opens Amazon product pages for items missing prices and extracts the detail-page price.
    """
    items_to_enrich = [item for item in items if item.get("url") and item.get("price") is None][:limit]
    if not items_to_enrich:
        return items

    print(f"   [Amazon] Enriching prices from product pages for {len(items_to_enrich)} items...")

    for item in items_to_enrich:
        try:
            await page.goto(item["url"], timeout=30000, wait_until="domcontentloaded")
            await human_delay(1200, 1800)

            detail = await page.evaluate(
                r"""() => {
                    const cleanText = (text) => String(text || '').replace(/\s+/g, ' ').trim();
                    const candidates = [
                        '#corePrice_feature_div .a-offscreen',
                        '#corePriceDisplay_desktop_feature_div .a-offscreen',
                        '#tp_price_block_total_price_ww .a-offscreen',
                        '.apexPriceToPay .a-offscreen',
                        '.priceToPay .a-offscreen',
                        '#corePrice_feature_div',
                        '#corePriceDisplay_desktop_feature_div',
                    ];

                    for (const selector of candidates) {
                        const nodes = Array.from(document.querySelectorAll(selector));
                        for (const node of nodes) {
                            const text = cleanText(node.innerText);
                            if (/\$\s*\d|USD\s*\d|US\$\s*\d/.test(text)) {
                                return { price_text: text };
                            }
                        }
                    }

                    const bodyText = cleanText(document.body?.innerText || '');
                    const bodyMatch = bodyText.match(/(?:\$|USD\s*|US\$\s*)(\d[\d,]*(?:\.\d{1,2})?)/);
                    return { price_text: bodyMatch ? bodyMatch[0] : null };
                }"""
            )

            price = parse_amazon_price_text((detail or {}).get("price_text"))
            if price is not None:
                item["price"] = price
                print(f"   [Amazon] Detail price found: {item['title'][:80]!r} -> {price}")
            else:
                print(f"   [Amazon] Detail price missing: {item['title'][:80]!r}")
        except Exception as exc:
            print(f"   [Amazon] Detail price lookup failed for {item['title'][:60]!r}: {exc}")

    return items


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

                    const cleanText = (text) => String(text || '').replace(/\s+/g, ' ').trim();

                    const pickLongestText = (values) => {
                        const candidates = values
                            .map(cleanText)
                            .filter(text => text && text.length >= 5 && !/^sponsored$/i.test(text));

                        if (!candidates.length) return null;
                        return candidates.sort((a, b) => b.length - a.length)[0];
                    };

                    const parseNumericPrice = (text) => {
                        if (!text) return null;

                        let cleaned = String(text).replace(/[^\d.,]/g, '');
                        if (!cleaned) return null;

                        const hasComma = cleaned.includes(',');
                        const hasDot = cleaned.includes('.');

                        if (hasComma && hasDot) {
                            if (cleaned.lastIndexOf('.') > cleaned.lastIndexOf(',')) {
                                cleaned = cleaned.replace(/,/g, '');
                            } else {
                                cleaned = cleaned.replace(/\./g, '').replace(',', '.');
                            }
                        } else if (hasComma) {
                            const parts = cleaned.split(',');
                            const last = parts[parts.length - 1];
                            cleaned = last.length === 2
                                ? parts.slice(0, -1).join('') + '.' + last
                                : parts.join('');
                        }

                        const value = parseFloat(cleaned);
                        return Number.isFinite(value) ? value : null;
                    };

                    const extractPriceFromText = (text) => {
                        const normalized = String(text || '').replace(/\u00A0/g, ' ');
                        const matches = Array.from(
                            normalized.matchAll(
                                /(?:^|[\s(])(?:\$|USD\s*|US\$\s*|₹|INR\s*)(\d[\d,]*(?:\.\d{1,2})?)/gi
                            )
                        );

                        for (const match of matches) {
                            const context = normalized.slice(
                                Math.max(0, match.index - 24),
                                Math.min(normalized.length, match.index + match[0].length + 24)
                            );
                            if (/delivery|shipping|ships to|coupon|save/i.test(context)) {
                                continue;
                            }

                            const parsed = parseNumericPrice(match[1]);
                            if (parsed && parsed > 0) {
                                return parsed;
                            }
                        }

                        return null;
                    };

                    cards.forEach(el => {
                        const cardText = cleanText(el.innerText);
                        const sponsorBadge = el.querySelector(
                            '[aria-label*="Sponsored"], [aria-label*="sponsored"], [data-component-type="sp-sponsored-result"], .puis-sponsored-label-text'
                        );
                        if (
                            sponsorBadge ||
                            /^sponsored\b/i.test(cardText) ||
                            /\bsponsored\b/i.test(
                                cleanText(
                                    el.querySelector('[data-cy="title-recipe"]')?.innerText ||
                                    ''
                                )
                            )
                        ) {
                            return;
                        }

                        const linkEl = el.querySelector(
                            '[data-cy="title-recipe"] a, h2 a, a.a-link-normal.s-no-outline, a.a-link-normal.s-underline-text, a[href*="/dp/"], a[href*="/gp/"]'
                        );
                        const imageEl = el.querySelector('img.s-image');
                        const title = pickLongestText([
                            el.querySelector('[data-cy="title-recipe"]')?.innerText,
                            el.querySelector('h2')?.innerText,
                            el.querySelector('h2 a')?.innerText,
                            el.querySelector('.a-size-medium.a-color-base.a-text-normal')?.innerText,
                            linkEl?.getAttribute('aria-label'),
                            linkEl?.getAttribute('title'),
                            linkEl?.innerText,
                            imageEl?.getAttribute('alt'),
                        ]);
                        if (!title || title.length < 5) return;

                        const priceCandidates = Array.from(
                            el.querySelectorAll(
                                [
                                    '[data-cy="price-recipe"] .a-price .a-offscreen',
                                    '[data-cy="price-recipe"] .a-price-whole',
                                    '.a-price.a-text-price .a-offscreen',
                                    '.a-price:not([data-a-strike="true"]) .a-offscreen',
                                    '.apexPriceToPay .a-offscreen',
                                    '.a-price-range .a-offscreen',
                                    '.reinventPricePriceToPayMargin .a-offscreen',
                                ].join(', ')
                            )
                        )
                            .map(node => cleanText(node.innerText))
                            .filter(text => /[\d]/.test(text));

                        let price = null;
                        for (const candidate of priceCandidates) {
                            const parsed = parseNumericPrice(candidate);
                            if (parsed && parsed > 0) {
                                price = parsed;
                                break;
                            }
                        }

                        if (!price) {
                            price = extractPriceFromText(
                                el.querySelector('[data-cy="price-recipe"]')?.innerText ||
                                el.innerText
                            );
                        }

                        const ratingEl = el.querySelector(
                            'i[class*="a-icon-star"] span, span[aria-label*="out of 5"], [aria-label*="stars"]'
                        );
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
                                'span[aria-label*="delivery"], span[aria-label*="shipping"], [data-cy="delivery-recipe"], [data-cy="delivery-estimate"], [data-cy="delivery-block"] span, .a-color-base.a-text-bold'
                            )
                        );
                        const shippingText = shippingCandidates
                            .map(node => node.innerText || node.getAttribute('aria-label') || '')
                            .find(text => /delivery|shipping|arrives|overnight|today|tomorrow|eligible|prime/i.test(text));
                        const shipping = shippingText ? shippingText.trim() : 'See listing';

                        const href = linkEl ? linkEl.getAttribute('href') : null;
                        const url = href
                            ? (href.startsWith('http') ? href : 'https://www.amazon.com' + href)
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
                        } else if (
                            titleLower.includes('brand new') ||
                            titleLower.includes('new sealed') ||
                            titleLower.includes('factory sealed')
                        ) {
                            condition = 'New';
                        }

                        items.push({ title, price, rating, shipping, condition, url });
                    });

                    const seen = new Set();
                    return items.filter(item => {
                        const key = `${item.title}::${item.url || ''}`;
                        if (seen.has(key)) return false;
                        seen.add(key);
                        return true;
                    });
                }"""
            )

            print(f"   [Amazon] Found {len(raw_items)} items")
            log_raw_scraper_items("Amazon", raw_items)
            filtered_items = [
                item
                for item in raw_items
                if is_relevant_product_title(query, item.get("title", ""))
            ]
            print(f"   [Amazon] Relevant items after filtering: {len(filtered_items)}")
            if len(filtered_items) != len(raw_items):
                log_raw_scraper_items("Amazon relevant", filtered_items)
            filtered_items = [
                {
                    **item,
                    "condition": infer_condition_from_text(
                        item.get("title"),
                        item.get("condition"),
                    ),
                }
                for item in filtered_items
                if is_truly_new_item(item.get("title"), item.get("condition"))
            ]
            print(f"   [Amazon] Truly new items after condition filter: {len(filtered_items)}")
            filtered_items = await enrich_amazon_missing_prices(
                page,
                filtered_items,
                limit=max(max_results * 2, 8),
            )
            log_raw_scraper_items("Amazon enriched", filtered_items[:max_results])
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
