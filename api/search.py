import asyncio
import uuid

from fastapi import APIRouter, Header, HTTPException

from core.cancellation import (
    FlowCancelled,
    create_cancel_context,
    get_cancel_context,
    pop_cancel_context,
)
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
async def search(
    request: SearchRequest,
    x_search_id: str | None = Header(default=None, alias="X-Search-Id"),
):
    """
    Full pipeline:
    1. Azure OpenAI parses the user query into structured criteria
    2. The research flow builds a search term and scrapes eBay, Best Buy, and Amazon via Playwright
    3. Raw products are strictly filtered and ranked against brand, model, price, storage, and condition rules
    4. If strict matches are too few, the display set is expanded with softer query-relevant fallback results
    5. Azure OpenAI generates a short summary from the final display set and recommendation
    6. Results are saved to local CSV + JSON files and returned as a structured API response
    """
    search_id = x_search_id or str(uuid.uuid4())
    cancel_context = create_cancel_context(search_id)

    print(f"\n[IGNA API] POST /search - {request.query} (search_id={search_id})")

    try:
        result = await asyncio.to_thread(
            run_research,
            request.query,
            request.max_results_per_site,
            cancel_context,
        )

        cancel_context.raise_if_cancelled()

        display_products = result["display_products"]
        display_recommendation = result["display_recommendation"]

        print("[IGNA API] Step 5 - saving reports...")
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
    except FlowCancelled as exc:
        print(f"[IGNA API] Search cancelled: {search_id}")
        raise HTTPException(status_code=499, detail=str(exc)) from exc
    finally:
        pop_cancel_context(search_id)


@router.post(
    "/search/{search_id}/cancel",
    tags=["Search"],
    summary="Cancel a running product search",
)
async def cancel_search(search_id: str):
    cancel_context = get_cancel_context(search_id)
    if cancel_context is None:
        return {"search_id": search_id, "status": "not_found"}

    cancel_context.cancel()
    print(f"[IGNA API] Cancel requested for search_id={search_id}")
    return {"search_id": search_id, "status": "cancelling"}
