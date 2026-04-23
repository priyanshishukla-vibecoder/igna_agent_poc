# models.py
# Pydantic schemas — defines the shape of every request and response
# FastAPI uses these for automatic validation and /docs generation

from pydantic import BaseModel, Field
from typing import Optional


# ── Request model ──────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """
    Body sent by the client to POST /search.
    All fields except query are optional — Azure OpenAI will infer
    missing criteria from the natural language query.
    """
    query: str = Field(
        ...,
        description="Natural language product search query",
        example="Find smartphones under $500 with at least 6GB RAM"
    )
    max_results_per_site: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max products to return per site"
    )


# ── Product model ──────────────────────────────────────────────────────────────

class Product(BaseModel):
    """A single product scraped from an eCommerce site."""
    site:      str
    name:      str
    price:     Optional[float] = None
    rating:    Optional[float] = None
    condition: Optional[str]   = None
    specs:     Optional[str]   = None
    shipping:  Optional[str]   = None
    url:       Optional[str]   = None


# ── Criteria model ─────────────────────────────────────────────────────────────

class SearchCriteria(BaseModel):
    """
    Structured criteria extracted from the user query by Azure OpenAI.
    Returned in the response so the client can see what was understood.
    """
    product:        Optional[str]   = None
    max_price:      Optional[float] = None
    min_ram_gb:     Optional[int]   = None
    min_storage_gb: Optional[int]   = None
    brand:          Optional[str]   = None
    condition:      Optional[str]   = None
    sites:          list[str]       = ["eBay", "Best Buy", "Amazon"]


# ── Response model ─────────────────────────────────────────────────────────────

class SearchResponse(BaseModel):
    """
    Full response returned by POST /search.
    Contains the parsed criteria, all matching products,
    the top recommendation, and a summary from Azure OpenAI.
    """
    query:          str
    criteria:       SearchCriteria
    total_found:    int
    products:       list[Product]
    recommendation: Optional[Product] = None
    summary:        Optional[str]     = None
    report_path:    Optional[str]     = None
    status:         str = "success"


# ── Health model ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response from GET /health."""
    status:       str
    azure_openai: str
    scraper:      str
    version:      str = "1.0.0"