import os

from fastapi import APIRouter
from openai import AzureOpenAI

from models import HealthResponse


router = APIRouter() #APIRouter lets you define a group of related API routes(instead of putting everything in one file)
#This router is later plugged into your main FastAPI app in app.py

@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service health check",
)
async def health():
    """Checks FastAPI is running and Azure OpenAI is reachable."""
    openai_status = "unreachable"

    try:
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
        )
        client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        openai_status = "connected"
    except Exception as exc:
        openai_status = f"error: {str(exc)[:80]}"

    return HealthResponse(
        status="healthy",
        azure_openai=openai_status,
        scraper="ready",
        version="1.0.0",
    )


@router.get("/", include_in_schema=False)
async def root():
    return {
        "message": "IGNA Competitive Product Research Agent",
        "version": "1.0.0",
        "by": "Ignatiuz — ignatiuz.com",
    }
