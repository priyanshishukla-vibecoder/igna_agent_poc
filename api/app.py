import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.health import router as health_router
from api.report import router as report_router
from api.search import router as search_router


app = FastAPI(
    title="IGNA Competitive Product Research Agent",
    description="AI-powered competitive product research API by Ignatiuz. Powered by Azure OpenAI GPT-5-mini.",
    version="1.0.0",
    contact={"name": "IGNA by Ignatiuz", "url": "https://www.ignatiuz.com"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(report_router)
app.include_router(health_router)
