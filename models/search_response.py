from pydantic import BaseModel

from models.product import Product
from models.search_criteria import SearchCriteria


class SearchResponse(BaseModel):
    """Full response returned by POST /search."""

    query: str
    criteria: SearchCriteria
    total_found: int
    products: list[Product]
    recommendation: Product | None = None
    summary: str | None = None
    report_path: str | None = None
    status: str = "success"
