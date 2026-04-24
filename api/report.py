import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse


router = APIRouter()


@router.get(
    "/report/{filename}",
    tags=["Reports"],
    summary="Fetch a saved report",
)
async def get_report(filename: str):
    """Returns a previously saved JSON or CSV report from the data/ directory."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join("data", safe_name)

    if not safe_name.endswith((".json", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="Only .json and .csv files supported.",
        )
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=404,
            detail=f"Report '{safe_name}' not found.",
        )

    if safe_name.endswith(".json"):
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)

    with open(filepath, "r", encoding="utf-8") as file:
        return PlainTextResponse(file.read())
