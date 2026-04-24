from pydantic import BaseModel


class SearchCriteria(BaseModel):
    """Structured criteria extracted from the user query by Azure OpenAI."""

    search_term: str | None = None
    product: str | None = None
    max_price: float | None = None
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    brand: str | None = None
    condition: str | None = None
    sites: list[str] = ["eBay", "Best Buy", "Amazon"]
