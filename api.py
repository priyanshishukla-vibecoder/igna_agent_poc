# api.py
# FastAPI Application — IGNA Competitive Product Research Agent
#
# Fix: Python 3.14 on Windows requires WindowsProactorEventLoopPolicy
# for Playwright to launch Chromium via subprocess.
# These 4 lines MUST be at the very top before any other imports.

import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from models import SearchRequest, SearchResponse, SearchCriteria, Product, HealthResponse
from igna_brain import parse_query, filter_products, recommend, generate_summary
from cua_scraper import run_scraper
from reporter import save_csv, save_json, print_table

load_dotenv()

app = FastAPI(
    title="IGNA Competitive Product Research Agent",
    description="AI-powered competitive product research API by Ignatiuz. Powered by Azure OpenAI GPT-5-mini.",
    version="1.0.0",
    contact={"name": "IGNA by Ignatiuz", "url": "https://www.ignatiuz.com"}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/search", response_model=SearchResponse, tags=["Search"],
          summary="Run a competitive product search")
async def search(request: SearchRequest):
    """
    Full pipeline:
    1. Azure OpenAI parses natural language query into structured criteria
    2. CUA scraper searches eBay x2 and Best Buy via Playwright
    3. IGNA brain filters, ranks, picks top recommendation
    4. Azure OpenAI generates a business summary
    5. Results saved to local JSON + CSV
    6. Structured JSON response returned
    """
    print(f"\n[IGNA API] POST /search — {request.query}")

    # Step 1 — Parse with Azure OpenAI
    print("[IGNA API] Step 1 — parsing query with Azure OpenAI...")
    criteria = parse_query(request.query)
    print(f"[IGNA API] Criteria: {criteria}")

    # Step 2 — CUA scraper
    # Must use await scrape_all() directly — NOT run_scraper()
    # run_scraper() uses asyncio.run() which fails inside FastAPI's event loop
    print("[IGNA API] Step 2 — CUA scraper launching...")
    search_term = request.query
    # Run Playwright in a worker thread to avoid Windows ASGI loop subprocess limits.
    raw_products = await asyncio.to_thread(
        run_scraper,
        search_term,
        request.max_results_per_site,
    )
    print(f"[IGNA API] Step 2 complete — {len(raw_products)} raw products")

    # Step 3 — Filter and rank
    print("[IGNA API] Step 3 — filtering and ranking...")
    filtered = filter_products(raw_products, criteria)
    top_pick = recommend(filtered)
    display_products = filtered if filtered else raw_products
    display_recommendation = top_pick if top_pick else recommend(raw_products)
    print(f"[IGNA API] Step 3 complete — {len(display_products)} products")

    # Step 4 — AI summary
    print("[IGNA API] Step 4 — generating AI summary...")
    summary = generate_summary(display_products, criteria, display_recommendation)

    # Step 5 — Save reports
    print("[IGNA API] Step 5 — saving reports...")
    save_csv(display_products)
    json_path = save_json(display_products, display_recommendation, summary, criteria)

    if display_products:
        print_table(display_products[:10], display_recommendation)

    # Step 6 — Return response
    return SearchResponse(
        query=request.query,
        criteria=SearchCriteria(**criteria),
        total_found=len(display_products),
        products=[Product(**p) for p in display_products[:20]],
        recommendation=Product(**display_recommendation) if display_recommendation else None,
        summary=summary,
        report_path=json_path,
        status="success"
    )


@app.get("/report/{filename}", tags=["Reports"], summary="Fetch a saved report")
async def get_report(filename: str):
    """Returns a previously saved JSON report from the data/ directory."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join("data", safe_name)
    if not safe_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files supported.")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Report '{safe_name}' not found.")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/health", response_model=HealthResponse, tags=["Health"],
         summary="Service health check")
async def health():
    """Checks FastAPI is running and Azure OpenAI is reachable."""
    from openai import AzureOpenAI
    openai_status = "unreachable"
    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )
        client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini"),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        openai_status = "connected"
    except Exception as e:
        openai_status = f"error: {str(e)[:80]}"
    return HealthResponse(
        status="healthy",
        azure_openai=openai_status,
        scraper="ready",
        version="1.0.0"
    )


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "IGNA Competitive Product Research Agent",
        "version": "1.0.0",
        "by":      "Ignatiuz — ignatiuz.com"
    }