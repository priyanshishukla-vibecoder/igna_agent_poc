import asyncio
import os
import random
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import Error, Playwright

from core.cancellation import CancelContext


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


_BROWSER_PROFILE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "browser_profile")
)


async def get_stealth_page(playwright: Playwright):
    """Launch a persistent Chrome profile so trust signals (cookies, localStorage,
    accepted delivery location) survive across runs.

    Amazon (and others) score a fresh, zero-history Playwright session as
    untrusted and reject privileged actions like changing the US delivery ZIP.
    Reusing the same profile dir lets the session accumulate trust on the
    first successful run (or via a one-time manual setup in the same profile).
    """
    os.makedirs(_BROWSER_PROFILE_DIR, exist_ok=True)
    print(f"   [Browser] Using persistent profile at {_BROWSER_PROFILE_DIR}")

    context_options = {
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        "user_agent": random.choice(USER_AGENTS),
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "screen": {"width": 1280, "height": 800},
        "color_scheme": "light",
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-ch-ua": '"Google Chrome";v="124", "Chromium";v="124", "Not.A/Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    }

    try:
        context = await playwright.chromium.launch_persistent_context(
            _BROWSER_PROFILE_DIR,
            channel="chrome",
            **context_options,
        )
    except Error:
        context = await playwright.chromium.launch_persistent_context(
            _BROWSER_PROFILE_DIR,
            **context_options,
        )

    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        window.chrome = { runtime: {} };
        """
    )

    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


def register_cancelable_browser(browser, cancel_context: CancelContext | None):
    """Closes the active Playwright browser when a flow is cancelled."""
    if cancel_context is None:
        return None

    loop = asyncio.get_running_loop()

    def close_browser() -> None:
        loop.call_soon_threadsafe(lambda: asyncio.create_task(browser.close()))

    cancel_context.register_callback(close_browser)
    return close_browser


async def human_delay(
    min_ms: int = 800,
    max_ms: int = 2000,
    cancel_context: CancelContext | None = None,
):
    """Random delay to mimic human browsing pace."""
    total_seconds = random.uniform(min_ms / 1000, max_ms / 1000)
    elapsed_seconds = 0.0

    while elapsed_seconds < total_seconds:
        if cancel_context is not None:
            cancel_context.raise_if_cancelled()

        step_seconds = min(0.2, total_seconds - elapsed_seconds)
        await asyncio.sleep(step_seconds)
        elapsed_seconds += step_seconds

    if cancel_context is not None:
        cancel_context.raise_if_cancelled()
