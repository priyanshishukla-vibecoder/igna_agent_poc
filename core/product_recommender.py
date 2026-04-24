from core.product_filter import score_product


def recommend(products: list, criteria: dict | None = None) -> dict | None:
    """Returns the best recommended product using the same relevance scoring rules."""
    if not products:
        return None

    if not criteria:
        return products[0]

    return max(
        products,
        key=lambda item: (
            score_product(item, criteria),
            -(item.get("price") or 9999),
            item.get("rating") or 0,
        ),
    )
