import asyncio

from fastapi import APIRouter

from core.research_flow import run_research
from core.report_writer import print_table, save_csv, save_json
from models import Product, SearchCriteria, SearchRequest, SearchResponse


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
    1. Azure OpenAI parses natural language query into structured criteria
    2. CUA scraper searches eBay x2 and Best Buy via Playwright
    3. IGNA brain filters, ranks, picks top recommendation
    4. Azure OpenAI generates a business summary
    5. Results saved to local JSON + CSV
    6. Structured JSON response returned
    """
    print(f"\n[IGNA API] POST /search — {request.query}")

    result = await asyncio.to_thread(
        run_research,
        request.query,
        request.max_results_per_site,
    )

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
