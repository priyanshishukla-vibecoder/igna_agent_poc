# IGNA Competitive Product Research Agent

IGNA is a FastAPI service for competitive product research across eBay, Best Buy, and Amazon. It takes a natural-language query, converts it into structured search criteria with Azure OpenAI, runs Playwright scrapers, filters and ranks the results, generates a short AI summary, and saves JSON/CSV reports in `data/`.

## What It Does

- Parses user intent from free-form product queries
- Scrapes multiple storefronts with Playwright
- Applies strict filtering for brand, model, price, storage, RAM, and condition
- Falls back to softer query-relevance when strict matches are too sparse
- Recommends a best pick from the final result set
- Saves timestamped JSON and CSV reports locally

## Current Tech Stack

- FastAPI
- Playwright
- Azure OpenAI
- Pydantic
- Rich

## Repository Layout

```text
igna_agent_poc2/
├── api/
│   ├── app.py              # FastAPI app bootstrap and router registration
│   ├── health.py           # /health and root endpoints
│   ├── report.py           # /report/{filename} endpoint
│   └── search.py           # /search and /search/{search_id}/cancel endpoints
├── core/
│   ├── cancellation.py     # CancelContext registry and cancellation helpers
│   ├── product_filter.py   # Strict filtering, soft fallback, deduping, scoring
│   ├── product_recommender.py
│   ├── query_parser.py     # Azure OpenAI + fallback query parsing
│   ├── report_writer.py    # CSV/JSON persistence and console tables
│   ├── research_flow.py    # End-to-end search orchestration
│   └── summary_generator.py
├── integrations/
│   ├── amazon_scraper.py
│   ├── bestbuy_scraper.py
│   ├── browser.py          # Shared Playwright browser helpers
│   ├── ebay_scraper.py
│   ├── scraper_runner.py   # Sequential scraper execution wrapper
│   └── scraper_support.py
├── models/
│   ├── product.py
│   ├── search_criteria.py
│   ├── search_request.py
│   └── search_response.py
├── data/                   # Generated CSV/JSON reports and scraper screenshots
├── frontend/               # Frontend assets if used by the local UI
├── main.py                 # CLI flow for local interactive usage
├── requirements.txt
└── README.md
```

## API Endpoints

- `POST /search`
- `POST /search/{search_id}/cancel`
- `GET /report/{filename}`
- `GET /health`
- `GET /`

## How `/search` Works

The `/search` endpoint is defined in `api/search.py` and uses a threaded orchestration flow so Playwright can run safely without blocking the FastAPI event loop.

### Request Model

`POST /search` accepts:

```json
{
  "query": "best wireless headphones under 200",
  "max_results_per_site": 5
}
```

- `query`: natural-language product request
- `max_results_per_site`: per-store cap from `1` to `20`

### Search Flow

1. The client sends `POST /search`.
2. The route creates a `search_id` from the `X-Search-Id` header if present, otherwise a UUID.
3. A `CancelContext` is created and registered for that `search_id`.
4. FastAPI calls `run_research(...)` via `asyncio.to_thread(...)` so the Playwright work runs off the main ASGI loop.
5. In `core/research_flow.py`, `parse_query(query)` converts the natural-language request into structured criteria.
6. The parsed criteria are normalized into a search term, typically `criteria["search_term"]`.
7. `run_scraper(...)` in `integrations/scraper_runner.py` launches the storefront scrapers.
8. Scrapers currently run sequentially in this order:
   - eBay
   - Best Buy
   - Amazon
9. Each scraper returns structured product dictionaries, and the runner deduplicates them by `(site, truncated name)`.
10. Back in `run_research(...)`, strict filtering is applied with `filter_products(...)`.
11. If strict matches are too few, the display set is expanded with `filter_query_relevant_products(...)`.
12. A recommendation is produced with `recommend(...)`.
13. Azure OpenAI generates a short summary from the final display products and recommendation.
14. Control returns to `POST /search`, which saves:
   - a CSV report via `save_csv(...)`
   - a JSON report via `save_json(...)`
15. The endpoint returns a `SearchResponse` containing:
   - parsed criteria
   - final products
   - recommendation
   - summary
   - saved report path

### Cancellation Flow

1. `POST /search/{search_id}/cancel` looks up the active `CancelContext`.
2. If found, it marks the request as cancelled.
3. Long-running browser actions periodically call `raise_if_cancelled()`.
4. The API returns HTTP `499` when a running search is cancelled.

## Result Selection Logic

The search pipeline distinguishes between multiple result sets:

- `raw_products`: everything returned from the scrapers after per-site normalization
- `filtered_products`: strict matches after criteria-based filtering
- `display_products`: the final list shown to the API consumer

Display behavior:

- If strict filtering returns enough products, the display set is the strict set
- If strict filtering returns too few products, the display set is expanded with softer relevance matches
- If strict filtering returns zero products, the display set is built entirely from soft relevance fallback

This lets the endpoint remain useful even when the exact product/model/price constraints are too narrow.

## Reports

Each successful search writes:

- `data/report_<timestamp>.csv`
- `data/report_<timestamp>.json`

The JSON report includes:

- `generated_at`
- `criteria`
- `total_found`
- `recommendation`
- `summary`
- `products`

You can fetch a saved report with:

```http
GET /report/report_20260429_123456.json
```

## Running Locally

### Prerequisites

- Python 3.9+
- Playwright Chromium
- Azure OpenAI credentials

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### Environment Variables

Create a `.env` file in the project root:

```env
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_ENDPOINT=your_endpoint_here
AZURE_OPENAI_API_VERSION=2024-05-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
```

### Start the API

```bash
uvicorn api.app:app --reload
cd frontend
npm run dev
```

### Example Request

```bash
curl -X POST "http://127.0.0.1:8000/search" ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"travel camera under 1000\",\"max_results_per_site\":5}"
```

## Notes on Runtime Behavior

- On Windows, the app sets `WindowsProactorEventLoopPolicy` in `api/app.py`.
- The scraper runner uses a `ProactorEventLoop` on Windows when invoked from the API thread.
- Playwright scraping is intentionally executed inside `asyncio.to_thread(...)` from the FastAPI route.
- Best Buy and Amazon contain extra debugging and resilience logic for storefront-specific behavior.

## Troubleshooting

- If `/search` fails after editing scraper files during a request, `uvicorn --reload` may have restarted the server mid-scrape.
- If Azure OpenAI credentials are missing or invalid, `/health` will report the OpenAI connection as an error.
- If browser automation becomes flaky, inspect files written into `data/` such as debug screenshots and generated reports.
