import os
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from core.cancellation import CancelContext, FlowCancelled
from integrations.browser import get_stealth_page, human_delay, register_cancelable_browser
from integrations.scraper_support import (
    BESTBUY_CATEGORIES,
    build_products,
    get_product_keyword,
    infer_condition_from_text,
    is_truly_new_item,
    log_raw_scraper_items,
    log_scraped_products,
)


def build_bestbuy_search_url(
    query: str,
    category_id: str = "",
    max_price: int | None = None,
) -> str:
    """Builds a Best Buy search URL, using direct price-facet URLs when possible."""
    params = []

    if category_id:
        category_param = "id" if category_id.startswith("pcat") else "cp"
        params.append(f"{category_param}={category_id}")

    if max_price is not None:
        price_facet = quote_plus(f"currentprice_facet=Price~0 to {int(max_price)}").replace(
            "~",
            "%7E",
        )
        params.append(f"qp={price_facet}")

    params.append(f"st={quote_plus(query)}")
    return f"https://www.bestbuy.com/site/searchpage.jsp?{'&'.join(params)}"


async def apply_bestbuy_filters(
    page,
    query: str,
    category_id: str,
    criteria: dict | None,
    cancel_context: CancelContext | None = None,
) -> None:
    """Uses Best Buy's on-page filters for availability and direct URL price filters."""
    print("   [Best Buy] Applying site filters...")

    try:
        exclude_out_of_stock = page.get_by_text("Exclude Out of Stock Items", exact=False).first
        await exclude_out_of_stock.click(timeout=4000)
        await human_delay(1200, 1800, cancel_context=cancel_context)
        await page.wait_for_load_state("networkidle", timeout=10000)
        print("   [Best Buy] Applied availability filter: exclude out of stock")
    except Exception as exc:
        print(f"   [Best Buy] Availability filter skipped: {exc}")

    max_price = (criteria or {}).get("max_price")
    if max_price is None:
        return

    try:
        price_filtered_url = build_bestbuy_search_url(
            query=(criteria or {}).get("search_term") or query,
            category_id=category_id,
            max_price=max_price,
        )
        print(f"   [Best Buy] Navigating to direct price-filter URL: {price_filtered_url}")
        await page.goto(price_filtered_url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=10000)
        await human_delay(1500, 2200, cancel_context=cancel_context)
        print(f"   [Best Buy] Applied max price filter: {int(max_price)}")
    except Exception as exc:
        print(f"   [Best Buy] Price filter skipped: {exc}")


async def extract_bestbuy_items(page) -> list:
    """Extracts visible Best Buy product cards from the current page state."""
    return await page.evaluate(
        r"""() => {
            const items = [];
            const rawCards = Array.from(
                document.querySelectorAll(
                    'li.sku-item, article.sku-item, article[data-sku-id], [data-testid^="sku-item-"], [data-sku-id]'
                )
            );
            const cards = [];
            const seenCardRoots = new Set();

            for (const candidate of rawCards) {
                const cardRoot =
                    candidate.closest('li.sku-item') ||
                    candidate.closest('article.sku-item') ||
                    candidate.closest('article[data-sku-id]') ||
                    candidate.closest('[data-testid^="sku-item-"]') ||
                    candidate;

                if (!(cardRoot instanceof Element) || seenCardRoots.has(cardRoot)) {
                    continue;
                }

                seenCardRoots.add(cardRoot);
                cards.push(cardRoot);
            }

            if (cards.length === 0) {
                cards.push(...Array.from(document.querySelectorAll('li, article')));
            }

            cards.forEach(el => {
                const text = el.innerText || '';
                if (!text.includes('$') || text.length < 20) return;
                if (el.querySelectorAll('li').length > 2) return;

                const normalizedText = text.replace(/\s+/g, ' ').trim().toLowerCase();
                const availabilityRoot =
                    el.querySelector('.sku-block-footer, .add-to-cart, .add-to-cart-compare') || el;
                const hasUnavailableTestId = Boolean(
                    availabilityRoot.querySelector('[data-testid*="plp-unavailable"]')
                );
                const unavailableButton = el.querySelector(
                    '.sku-block-footer button[data-testid*="plp-unavailable"], ' +
                    '.sku-block-footer button[disabled], ' +
                    '.sku-block-footer [aria-disabled="true"], ' +
                    '.add-to-cart button[data-testid*="plp-unavailable"], ' +
                    '.add-to-cart button[disabled], ' +
                    '.add-to-cart [aria-disabled="true"]'
                );
                const unavailableText = unavailableButton
                    ? (
                        unavailableButton.innerText ||
                        unavailableButton.textContent ||
                        unavailableButton.getAttribute('aria-label') ||
                        ''
                    )
                    : '';
                const normalizedUnavailableText = String(unavailableText)
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                const availabilityText = (availabilityRoot.innerText || availabilityRoot.textContent || '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                const looksUnavailable =
                    hasUnavailableTestId ||
                    normalizedUnavailableText.includes('unavailable') ||
                    availabilityText.includes('unavailable') ||
                    availabilityText.includes('notify me') ||
                    normalizedText.includes(' unavailable ') ||
                    normalizedText.endsWith(' unavailable') ||
                    normalizedText.includes(' notify me');

                if (looksUnavailable) {
                    return;
                }

                const titleEl = el.querySelector(
                    '.sku-header a, [class*="sku-title"] a, h4 a, h3 a, h4, h3'
                );
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

                const normalizeUrl = (href) => {
                    if (!href) return null;
                    try {
                        return new URL(href, window.location.origin).href;
                    } catch {
                        return null;
                    }
                };

                const skuId =
                    el.getAttribute('data-sku-id') ||
                    el.dataset?.skuId ||
                    el.querySelector('[data-sku-id]')?.getAttribute('data-sku-id') ||
                    null;

                const linkCandidates = [
                    titleEl?.closest('a'),
                    titleEl?.querySelector?.('a'),
                    el.querySelector('.sku-header a'),
                    el.querySelector('[class*="sku-title"] a'),
                    el.querySelector('h4 a, h3 a'),
                    ...Array.from(el.querySelectorAll('a')),
                ].filter(Boolean);

                const seenLinks = new Set();
                let url = null;
                for (const candidate of linkCandidates) {
                    const href = candidate.href || candidate.getAttribute('href');
                    const normalizedHref = normalizeUrl(href);
                    if (!normalizedHref || seenLinks.has(normalizedHref)) {
                        continue;
                    }
                    seenLinks.add(normalizedHref);

                    const candidateText = (
                        candidate.innerText ||
                        candidate.getAttribute('aria-label') ||
                        candidate.getAttribute('title') ||
                        ''
                    ).trim().toLowerCase();

                    const looksLikeProductUrl =
                        normalizedHref.includes('/site/') ||
                        normalizedHref.includes('skuId=') ||
                        normalizedHref.includes('/product/');

                    const textMatchesTitle =
                        candidateText && (
                            title.toLowerCase().includes(candidateText) ||
                            candidateText.includes(title.toLowerCase().slice(0, 24))
                        );

                    const skuMatches =
                        skuId &&
                        (
                            normalizedHref.includes(`skuId=${skuId}`) ||
                            normalizedHref.includes(`/${skuId}.p`)
                        );

                    if (looksLikeProductUrl && (skuMatches || textMatchesTitle || !url)) {
                        url = normalizedHref;
                        if (skuMatches || textMatchesTitle) {
                            break;
                        }
                    }
                }

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


async def open_bestbuy_search(
    page,
    search_url: str,
    cancel_context: CancelContext | None = None,
) -> None:
    """Opens the Best Buy search page and handles the country gate if it appears."""
    await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
    await human_delay(2000, 3000, cancel_context=cancel_context)

    page_content = await page.content()
    if "Choose a country" not in page_content:
        return

    print("   [Best Buy] Country popup - clicking United States...")
    try:
        await page.get_by_text("United States", exact=False).first.click()
        await page.wait_for_load_state("networkidle", timeout=10000)
        await human_delay(1500, 2500, cancel_context=cancel_context)
        if "searchpage" not in page.url:
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await human_delay(2000, 3000, cancel_context=cancel_context)
    except Exception as popup_err:
        print(f"   [Best Buy] Popup: {popup_err}")
        await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
        await human_delay(2000, 3000, cancel_context=cancel_context)


async def scrape_bestbuy(
    query: str,
    max_results: int = 5,
    criteria: dict | None = None,
    cancel_context: CancelContext | None = None,
) -> list:
    """Scrapes Best Buy with search-first, filter-second, fallback-to-unfiltered flow."""
    products = []
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as playwright:
        browser, page = await get_stealth_page(playwright)
        close_browser_callback = register_cancelable_browser(browser, cancel_context)
        try:
            if cancel_context is not None:
                cancel_context.raise_if_cancelled()

            keyword_source = (criteria or {}).get("product") or query
            keyword = get_product_keyword(keyword_source)
            category_id = BESTBUY_CATEGORIES.get(keyword, "")
            search_url = build_bestbuy_search_url(query, category_id=category_id)

            print("   [Best Buy] Navigating...")
            if category_id:
                print(f"   [Best Buy] Category: {category_id} ({keyword})")

            await open_bestbuy_search(page, search_url, cancel_context=cancel_context)
            await page.evaluate("window.scrollBy(0, 600)")
            await human_delay(2000, 2500, cancel_context=cancel_context)

            print("   [Best Buy] Capturing baseline search results...")
            raw_items = await extract_bestbuy_items(page)

            if raw_items:
                await apply_bestbuy_filters(
                    page,
                    query,
                    category_id,
                    criteria,
                    cancel_context=cancel_context,
                )
                await page.evaluate("window.scrollBy(0, 600)")
                await human_delay(2000, 2500, cancel_context=cancel_context)
                filtered_raw_items = await extract_bestbuy_items(page)

                if filtered_raw_items:
                    raw_items = filtered_raw_items
                    print(f"   [Best Buy] Using filtered results: {len(raw_items)} items")
                else:
                    print("   [Best Buy] Filters produced 0 items, reverting to unfiltered search results")
                    await open_bestbuy_search(page, search_url, cancel_context=cancel_context)
                    await page.evaluate("window.scrollBy(0, 600)")
                    await human_delay(2000, 2500, cancel_context=cancel_context)
                    raw_items = await extract_bestbuy_items(page)
            else:
                print("   [Best Buy] Baseline search returned 0 items, skipping filter application")

            await page.screenshot(path="data/debug_bestbuy.png")

            print(f"   [Best Buy] Found {len(raw_items)} items")
            log_raw_scraper_items("Best Buy", raw_items)
            normalized_items = [
                {
                    **item,
                    "condition": infer_condition_from_text(
                        item.get("title"),
                        item.get("condition"),
                    ),
                }
                for item in raw_items
            ]
            new_only_items = [
                item
                for item in normalized_items
                if is_truly_new_item(item.get("title"), item.get("condition"))
            ]
            print(f"   [Best Buy] Truly new items after condition filter: {len(new_only_items)}")
            selected_items = new_only_items if len(new_only_items) >= max_results else normalized_items
            if selected_items is normalized_items and normalized_items:
                print(
                    "   [Best Buy] Using broader search results for fallback because "
                    "strict new-only matches were limited"
                )
            products = build_products(selected_items, "Best Buy", max_results)
            log_scraped_products("Best Buy", products)

        except FlowCancelled:
            print("   [Best Buy] Cancelled")
            raise
        except Exception as exc:
            print(f"   [Best Buy] Error: {exc}")
            try:
                await page.screenshot(path="data/error_bestbuy.png")
            except Exception:
                pass
        finally:
            if cancel_context is not None and close_browser_callback is not None:
                cancel_context.unregister_callback(close_browser_callback)
            await browser.close()

    return products
