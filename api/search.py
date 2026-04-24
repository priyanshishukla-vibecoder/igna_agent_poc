import asyncio # Used for async execution.

from fastapi import APIRouter

from core.research_flow import run_research 
# run_research is the main pipeline function(engine)

from core.report_writer import print_table, save_csv, save_json
# utility functions to save results and print tables

from models import Product, SearchCriteria, SearchRequest, SearchResponse
# Pydantic models for request and response validation and serialization


router = APIRouter()


@router.post(
    "/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Run a competitive product search",
)

async def search(request: SearchRequest):
    """
    Full pipeline:
    1. Azure OpenAI parses the user query into structured criteria
    2. The research flow builds a search term and scrapes eBay, Best Buy, and Amazon via Playwright
    3. Raw products are strictly filtered and ranked against brand, model, price, storage, and condition rules
    4. If strict matches are too few, the display set is expanded with softer query-relevant fallback results
    5. Azure OpenAI generates a short summary from the final display set and recommendation
    6. Results are saved to local CSV + JSON files and returned as a structured API response
    """
    print(f"\n[IGNA API] POST /search — {request.query}") #prints incoming request on console

    result = await asyncio.to_thread(
        run_research,
        request.query,
        request.max_results_per_site,
    )
    # to_thread() runs run_research in a separate thread

    display_products = result["display_products"]
    display_recommendation = result["display_recommendation"]

    print("[IGNA API] Step 5 — saving reports...")
    save_csv(display_products)
    json_path = save_json(
        display_products,
        display_recommendation,
        result["summary"],
        result["criteria"],
    )

    if display_products:
        print_table(display_products[:10], display_recommendation)

    return SearchResponse(
        query=request.query,
        criteria=SearchCriteria(**result["criteria"]),
        total_found=len(display_products),
        products=[Product(**product) for product in display_products[:20]],
        recommendation=(
            Product(**display_recommendation) if display_recommendation else None
        ),
        summary=result["summary"],
        report_path=json_path,
        status="success",
    )
