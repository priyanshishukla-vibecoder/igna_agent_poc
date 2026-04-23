from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str
    azure_openai: str
    scraper: str
    version: str = "1.0.0"
