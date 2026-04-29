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
                const describeControl = node => {
                    const controlText = (
                        node.innerText ||
                        node.textContent ||
                        node.getAttribute('aria-label') ||
                        node.getAttribute('title') ||
                        ''
                    )
                        .replace(/\s+/g, ' ')
                        .trim();

                    return {
                        tag: (node.tagName || '').toLowerCase(),
                        text: controlText,
                        aria_label: node.getAttribute('aria-label') || '',
                        title: node.getAttribute('title') || '',
                        role: node.getAttribute('role') || '',
                        testid: node.getAttribute('data-testid') || '',
                        class_name: node.className || '',
                        disabled: Boolean(node.disabled),
                        aria_disabled: node.getAttribute('aria-disabled') || '',
                    };
                };
                const cardControls = Array.from(
                    el.querySelectorAll('button, [role="button"], a')
                )
                    .map(describeControl)
                    .filter(control => control.text || control.aria_label || control.testid);
                const hasUnavailableTestId = Boolean(
                    availabilityRoot.querySelector('[data-testid*="plp-unavailable"]')
                );
                const ctaCandidates = Array.from(
                    availabilityRoot.querySelectorAll('button, [role="button"], a')
                )
                    .map(node => {
                        const text = (
                            node.innerText ||
                            node.textContent ||
                            node.getAttribute('aria-label') ||
                            node.getAttribute('title') ||
                            ''
                        )
                            .replace(/\s+/g, ' ')
                            .trim()
                            .toLowerCase();
                        return { node, text };
                    })
                    .filter(candidate => {
                        const text = candidate.text;
                        return (
                            text.includes('add to cart') ||
                            text.includes('see details') ||
                            text.includes('notify me') ||
                            text.includes('unavailable')
                        );
                    });
                const ctaCandidatesDetailed = ctaCandidates.map(candidate => describeControl(candidate.node));
                const ctaPriority = ['add to cart', 'see details', 'notify me', 'unavailable'];
                let normalizedPrimaryCtaText = '';
                for (const priority of ctaPriority) {
                    const match = ctaCandidates.find(candidate => candidate.text.includes(priority));
                    if (match) {
                        normalizedPrimaryCtaText = match.text;
                        break;
                    }
                }
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
                let ctaText = normalizedPrimaryCtaText;
                if (!ctaText && hasUnavailableTestId) {
                    ctaText = 'unavailable';
                } else if (!ctaText && normalizedUnavailableText.includes('unavailable')) {
                    ctaText = 'unavailable';
                } else if (!ctaText && availabilityText.includes('notify me')) {
                    ctaText = 'notify me';
                } else if (!ctaText && availabilityText.includes('unavailable')) {
                    ctaText = 'unavailable';
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

                items.push({
                    title,
                    price,
                    rating,
                    shipping,
                    condition,
                    url,
                    sku_id: skuId,
                    cta_text: ctaText,
                    primary_cta_text: normalizedPrimaryCtaText,
                    availability_text: availabilityText,
                    unavailable_text: normalizedUnavailableText,
                    has_unavailable_testid: hasUnavailableTestId,
                    cta_candidates: ctaCandidatesDetailed,
                    card_controls: cardControls,
                    card_text_preview: text.replace(/\s+/g, ' ').trim().slice(0, 600),
                });
            });

            const seen = new Set();
            return items.filter(item => {
                if (seen.has(item.title)) return false;
                seen.add(item.title);
                return true;
            });
        }"""
    )


async def extract_bestbuy_page_context(page) -> dict:
    """Captures Best Buy session/location context visible on the page for debugging."""
    return await page.evaluate(
        r"""() => {
            const getText = selectors => {
                for (const selector of selectors) {
                    const node = document.querySelector(selector);
                    const text = (
                        node?.innerText ||
                        node?.textContent ||
                        node?.getAttribute?.('aria-label') ||
                        node?.getAttribute?.('title') ||
                        ''
                    )
                        .replace(/\s+/g, ' ')
                        .trim();
                    if (text) return text;
                }
                return '';
            };

            const findTextsContaining = needles => {
                const elements = Array.from(document.querySelectorAll('button, a, div, span, p'));
                const matches = [];

                for (const el of elements) {
                    const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!text) continue;

                    const normalized = text.toLowerCase();
                    if (needles.some(needle => normalized.includes(needle))) {
                        matches.push(text);
                    }

                    if (matches.length >= 12) break;
                }

                return matches;
            };

            return {
                page_url: window.location.href,
                page_title: document.title,
                choose_country_visible: document.body.innerText.includes('Choose a country'),
                location_button_text: getText([
                    '[data-testid="store-button"]',
                    '[data-testid="fulfillment-location-button"]',
                    'button[aria-label*="store"]',
                    'button[aria-label*="Store"]',
                    'button[aria-label*="pickup"]',
                    'button[aria-label*="Pickup"]',
                ]),
                store_text: getText([
                    '[data-testid="storeName"]',
                    '[data-testid="selected-store"]',
                    '[class*="storeName"]',
                    '[class*="selected-store"]',
                ]),
                zip_text: getText([
                    '[data-testid="postalCode"]',
                    '[class*="postalCode"]',
                    '[class*="zipcode"]',
                    '[class*="zipCode"]',
                ]),
                shipping_texts: findTextsContaining(['shipping', 'pickup', 'delivery', 'store']),
                country_texts: findTextsContaining(['united states', 'canada', 'choose a country']),
            };
        }"""
    )


def filter_bestbuy_raw_items(raw_items: list[dict]) -> list[dict]:
    """Keeps only Best Buy items whose CTA is allowed for purchase/details."""
    allowed_ctas = {"add to cart", "see details"}
    blocked_ctas = {"notify me", "unavailable"}
    filtered_items = []

    for item in raw_items:
        cta_text = str(item.get("cta_text") or item.get("primary_cta_text") or "")
        normalized_cta_text = cta_text.strip().lower()

        if any(blocked in normalized_cta_text for blocked in blocked_ctas):
            continue

        if any(allowed in normalized_cta_text for allowed in allowed_ctas):
            filtered_items.append(item)

    return filtered_items


def log_bestbuy_filter_decisions(raw_items: list[dict], label: str) -> None:
    """Prints CTA-focused debug info for Best Buy raw items before/after filtering."""
    print(f"   [Best Buy] {label}: {len(raw_items)} items")
    for index, item in enumerate(raw_items[:10], start=1):
        print(
            "   [Best Buy] "
            f"{label} item {index}: "
            f"title={item.get('title')!r}, "
            f"cta_text={item.get('cta_text')!r}, "
            f"primary_cta_text={item.get('primary_cta_text')!r}, "
            f"availability_text={item.get('availability_text')!r}, "
            f"unavailable_text={item.get('unavailable_text')!r}, "
            f"has_unavailable_testid={item.get('has_unavailable_testid')!r}, "
            f"cta_candidates={item.get('cta_candidates')!r}"
        )

    remaining = len(raw_items) - 10
    if remaining > 0:
        print(f"   [Best Buy] {label}: ... {remaining} more items not shown")


def log_bestbuy_page_context(context: dict, label: str) -> None:
    """Prints Best Buy page/session context to help explain availability differences."""
    print(
        "   [Best Buy] "
        f"{label}: "
        f"url={context.get('page_url')!r}, "
        f"title={context.get('page_title')!r}, "
        f"choose_country_visible={context.get('choose_country_visible')!r}, "
        f"location_button_text={context.get('location_button_text')!r}, "
        f"store_text={context.get('store_text')!r}, "
        f"zip_text={context.get('zip_text')!r}"
    )
    print(
        "   [Best Buy] "
        f"{label} shipping/store texts: {context.get('shipping_texts')!r}"
    )
    print(
        "   [Best Buy] "
        f"{label} country texts: {context.get('country_texts')!r}"
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
            page_context = await extract_bestbuy_page_context(page)
            log_bestbuy_page_context(page_context, "Page context after navigation")
            await page.evaluate("window.scrollBy(0, 600)")
            await human_delay(2000, 2500, cancel_context=cancel_context)

            print("   [Best Buy] Capturing baseline search results...")
            raw_items = await extract_bestbuy_items(page)
            log_raw_scraper_items("Best Buy baseline raw", raw_items)
            log_bestbuy_filter_decisions(raw_items, "Baseline CTA debug")
            raw_items = filter_bestbuy_raw_items(raw_items)
            log_bestbuy_filter_decisions(raw_items, "Baseline allowed CTA")

            if raw_items:
                await apply_bestbuy_filters(
                    page,
                    query,
                    category_id,
                    criteria,
                    cancel_context=cancel_context,
                )
                page_context = await extract_bestbuy_page_context(page)
                log_bestbuy_page_context(page_context, "Page context after filters")
                await page.evaluate("window.scrollBy(0, 600)")
                await human_delay(2000, 2500, cancel_context=cancel_context)
                filtered_raw_items = await extract_bestbuy_items(page)
                log_raw_scraper_items("Best Buy filtered-page raw", filtered_raw_items)
                log_bestbuy_filter_decisions(filtered_raw_items, "Filtered-page CTA debug")
                filtered_raw_items = filter_bestbuy_raw_items(filtered_raw_items)
                log_bestbuy_filter_decisions(filtered_raw_items, "Filtered-page allowed CTA")

                if filtered_raw_items:
                    raw_items = filtered_raw_items
                    print(f"   [Best Buy] Using filtered results: {len(raw_items)} items")
                else:
                    print("   [Best Buy] Filters produced 0 items, reverting to unfiltered search results")
                    await open_bestbuy_search(page, search_url, cancel_context=cancel_context)
                    page_context = await extract_bestbuy_page_context(page)
                    log_bestbuy_page_context(page_context, "Page context after revert")
                    await page.evaluate("window.scrollBy(0, 600)")
                    await human_delay(2000, 2500, cancel_context=cancel_context)
                    raw_items = await extract_bestbuy_items(page)
                    log_raw_scraper_items("Best Buy reverted raw", raw_items)
                    log_bestbuy_filter_decisions(raw_items, "Reverted CTA debug")
                    raw_items = filter_bestbuy_raw_items(raw_items)
                    log_bestbuy_filter_decisions(raw_items, "Reverted allowed CTA")
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
