"""One-time manual seeding for the persistent Playwright profile.

Run once with:  python seed_amazon_profile.py

Opens a Chromium window using the same `data/browser_profile` directory the
scrapers use. Manually:
  1. Navigate to https://www.amazon.com/
  2. Click the 'Deliver to' pill in the top-left
  3. Type 19341, click Apply, then Done
  4. Close the window

After that, every scraper run will inherit the applied ZIP because the
session cookies persist in the same profile.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

from integrations.browser import get_stealth_page


async def main() -> None:
    print("\nOpening the persistent profile. Manually set ZIP 19341 and close the window when done.\n")
    async with async_playwright() as playwright:
        context, page = await get_stealth_page(playwright)
        await page.goto("https://www.amazon.com/", wait_until="domcontentloaded")
        try:
            await context.wait_for_event("close", timeout=0)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
