from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Body sent by the client to POST /search."""

    query: str = Field(
        ...,
        description="Natural language product search query",
        example="Find smartphones under $500 with at least 6GB RAM",
    )
    max_results_per_site: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max products to return per site",
    )
