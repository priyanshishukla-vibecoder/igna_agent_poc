import json
import os

from fastapi import APIRouter, HTTPException


router = APIRouter()


@router.get(
    "/report/{filename}",
    tags=["Reports"],
    summary="Fetch a saved report",
)
async def get_report(filename: str):
    """Returns a previously saved JSON report from the data/ directory."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join("data", safe_name)

    if not safe_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files supported.")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Report '{safe_name}' not found.")

    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)
