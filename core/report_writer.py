import csv
import json
import os
from datetime import datetime

from rich import box
from rich.console import Console
from rich.table import Table


console = Console()


def print_table(products: list, recommendation: dict):
    """Prints a formatted comparison table in the terminal."""
    table = Table(
        title="IGNA Competitive Product Research Report",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Rank", style="dim", width=5)
    table.add_column("Product", min_width=35)
    table.add_column("Site", width=10)
    table.add_column("Condition", width=14)
    table.add_column("Price", justify="right", width=9)
    table.add_column("Shipping", width=18)
    table.add_column("Rating", justify="center", width=8)

    for index, product in enumerate(products, start=1):
        is_top = product == recommendation
        rank_str = "[bold green]★ 1[/bold green]" if is_top else str(index)
        name_str = (
            f"[bold green]{product['name'][:50]}[/bold green]"
            if is_top
            else product["name"][:50]
        )
        price_str = f"${product['price']:.2f}" if product.get("price") else "N/A"
        rating_str = str(product["rating"]) if product.get("rating") else "—"

        table.add_row(
            rank_str,
            name_str,
            product.get("site", "—"),
            product.get("condition", "—"),
            price_str,
            product.get("shipping", "—"),
            rating_str,
        )

    console.print(table)

    if recommendation:
        console.print(
            f"\n[bold green]✔ IGNA Recommendation:[/bold green] "
            f"{recommendation['name'][:65]}\n"
            f"   Price: ${recommendation.get('price', 'N/A')} | "
            f"Condition: {recommendation.get('condition', '—')} | "
            f"Site: {recommendation.get('site', '—')}"
        )
        if recommendation.get("url"):
            console.print(f"   Link: {recommendation['url'][:80]}")


def save_csv(products: list, filename: str = None) -> str:
    """Saves the product list to a timestamped CSV file."""
    os.makedirs("data", exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/report_{timestamp}.csv"

    if not products:
        return filename

    keys = ["site", "name", "price", "condition", "rating", "specs", "shipping", "url"]
    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)

    console.print(f"\n[dim]✔ CSV saved → {filename}[/dim]")
    return filename


def save_json(
    products: list,
    recommendation: dict,
    summary: str,
    criteria: dict,
    filename: str = None,
) -> str:
    """Saves full results to a timestamped JSON file."""
    os.makedirs("data", exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/report_{timestamp}.json"

    report = {
        "generated_at": datetime.now().isoformat(),
        "criteria": criteria,
        "total_found": len(products),
        "recommendation": recommendation,
        "summary": summary,
        "products": products,
    }

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    console.print(f"[dim]✔ JSON saved → {filename}[/dim]")
    return filename


def build_api_response(
    query: str,
    criteria: dict,
    products: list,
    recommendation: dict,
    summary: str,
    report_path: str,
) -> dict:
    """Builds the final dict returned by FastAPI as a JSON response."""
    return {
        "query": query,
        "criteria": criteria,
        "total_found": len(products),
        "products": products[:20],
        "recommendation": recommendation,
        "summary": summary,
        "report_path": report_path,
        "status": "success",
    }
